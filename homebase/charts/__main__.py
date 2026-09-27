"""python -m homebase.charts [--replay YYYY-MM-DD [--speed 20] [--start 09:25]] [--port 8852]
                            [--fake-desk PORT]  (replay only, never the real desk's port)"""
from __future__ import annotations

import argparse
import datetime as dt

import uvicorn

from ..paths import state_dir
from . import DEFAULT_ROOTS, PORT
from .calendar import http_get
from .desk import DeskLink
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
    ap.add_argument("--fake-desk", type=int, metavar="PORT",
                    help="replay only: link chart trading to the FAKE desk (python -m tools.fake_desk) "
                         "on this port")
    a = ap.parse_args(argv)
    if a.fake_desk is not None and not a.replay:
        ap.error("--fake-desk needs --replay (a fake desk never runs beside the live feed)")
    if a.fake_desk == 8850:
        ap.error("--fake-desk must not be the real desk's port 8850")
    app = create_app(roots=[r for r in a.roots.split(",") if r],
                     replay=dt.date.fromisoformat(a.replay) if a.replay else None,
                     speed=a.speed, start_et=dt.time.fromisoformat(a.start),
                     # a replay never fetches ForexFactory: the cached weeks on disk are served as is
                     calendar_fetch=None if a.replay else http_get,
                     desk_factory=None if a.replay else (
                         lambda fan: DeskLink(fan, key_path=state_dir() / "desk.key")),
                     fake_desk_factory=(lambda fan: DeskLink(
                         fan, key_path=state_dir() / "fake-desk.key", url=f"http://127.0.0.1:{a.fake_desk}"))
                     if a.fake_desk is not None else None)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
