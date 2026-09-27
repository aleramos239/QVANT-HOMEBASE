"""python -m homebase.charts [--replay YYYY-MM-DD [--speed 20] [--start 09:25] [--paper-day]] [--port 8852]"""
from __future__ import annotations

import argparse
import datetime as dt

import uvicorn

from ..paths import state_dir
from . import DEFAULT_ROOTS, PORT
from .calendar import http_get
from .desk import DeskLink
from .news import http_get as news_http_get
from .paper import spawn_backtest
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
    ap.add_argument("--paper-day", action="store_true",
                    help="replay only: the replayed date counts as a GC NFP/CPI event day for the "
                         "paper runner (browser checks; stores nothing) -- use with --start 08:25")
    a = ap.parse_args(argv)
    if a.paper_day and not a.replay:
        ap.error("--paper-day works only with --replay")
    app = create_app(roots=[r for r in a.roots.split(",") if r],
                     replay=dt.date.fromisoformat(a.replay) if a.replay else None,
                     speed=a.speed, start_et=dt.time.fromisoformat(a.start),
                     # a replay never fetches ForexFactory or the news feeds: cached data is served as is
                     calendar_fetch=None if a.replay else http_get,
                     news_fetch=None if a.replay else news_http_get,
                     paper_day=a.paper_day,
                     # the paper runner's 2021-2024 comparison, computed once in its own process
                     paper_backtest=None if a.replay else spawn_backtest,
                     desk_factory=None if a.replay else (
                         lambda fan: DeskLink(fan, key_path=state_dir() / "desk.key")))
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
