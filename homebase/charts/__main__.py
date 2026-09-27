"""python -m homebase.charts [--replay YYYY-MM-DD [--speed 20] [--start 09:25] [--paper-day]] [--port 8852]
                            [--fake-desk PORT]  (replay only, never the real desk's port)"""
from __future__ import annotations

import argparse
import datetime as dt

import uvicorn

from ..backtest.discipline import RESEARCH_END
from ..paths import state_dir
from . import DEFAULT_ROOTS, PORT
from .calendar import http_get
from .desk import DeskLink
from .news import http_get as news_http_get
from .paper import spawn_backtest
from .server import create_app

# the real desk, the chart service, the replays: kept equal to tools/fake_desk.py's FORBIDDEN_PORTS (a test checks)
FAKE_DESK_REFUSED_PORTS = frozenset({8850, 8852, 8853, 8854})


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
    ap.add_argument("--paper-day", action="store_true",
                    help="replay only: the replayed date counts as a GC NFP/CPI event day for the "
                         "paper runner (browser checks; stores nothing) -- use with --start 08:25")
    ap.add_argument("--paper-allow-holdout", action="store_true",
                    help="with --paper-day: allow a replayed date after 2024-12-31 (holdout data; "
                         "each use needs the user's approval)")
    a = ap.parse_args(argv)
    if a.fake_desk is not None and not a.replay:
        ap.error("--fake-desk needs --replay (a fake desk never runs beside the live feed)")
    if a.fake_desk in FAKE_DESK_REFUSED_PORTS:
        ap.error(f"--fake-desk must not be {a.fake_desk}: a real service's port "
                 "(8850 the desk, 8852 the chart service, 8853/8854 the replays)")
    if a.paper_day and not a.replay:
        ap.error("--paper-day works only with --replay")
    if a.paper_allow_holdout and not a.paper_day:
        ap.error("--paper-allow-holdout works only with --paper-day")
    if a.paper_day and dt.date.fromisoformat(a.replay) > RESEARCH_END and not a.paper_allow_holdout:
        ap.error(f"--paper-day on {a.replay}: dates after {RESEARCH_END} are holdout data "
                 "(add --paper-allow-holdout only with the user's approval)")
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
                         lambda fan: DeskLink(fan, key_path=state_dir() / "desk.key")),
                     fake_desk_factory=(lambda fan: DeskLink(
                         fan, key_path=state_dir() / "fake-desk.key", url=f"http://127.0.0.1:{a.fake_desk}"))
                     if a.fake_desk is not None else None)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
