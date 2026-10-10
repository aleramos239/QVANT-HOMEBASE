"""The runner (shadow): one strategy's day on live prices, then the process that hosts every promoted one.

The children here are plain subprocesses (no sandbox) except in the one test that starts a sandboxed child. Nothing
places an order and nothing talks to a service: the ticks are lists, the store is a temp folder, the chart service's
stream is a fake transport."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from homebase.backtest import sandbox
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import et_ns
from homebase.labrun import __main__ as cli
from homebase.labrun import host, store
from homebase.labrun.host import Runner, StrategyDay, run_day
from homebase.labrun.tickclient import TickClient
from tests.test_labrun_shadowfills import cls_of, tape

REPO = Path(__file__).resolve().parent.parent
D = dt.date(2024, 3, 5)                      # a Tuesday
MS = 1_000_000
HEAD = "from homebase.strategies.base import Strategy\n\n\n"


def at(hms: str, ms: int = 0, d: dt.date = D) -> int:
    return et_ns(d, hms) + ms * MS


def ms_of(hms: str, ms: int = 0, d: dt.date = D) -> int:
    return at(hms, ms, d) // MS


def plain(argv, run_dir):
    """A child with no sandbox: the tests' own strategies only."""
    return subprocess.Popen(argv, cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def rec(source: str, name: str = "lab_x", **kw) -> dict:
    return {"name": name, "id": f"draft_{name}", "label": name, "root": "NQ", "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(), "params": {}, "qty": 1, "run": {}, "notes": [],
            "promoted_utc": "2026-10-09T12:00:00+00:00", "enabled": True, **kw}


def ticks(start: str, prices, step_ms: int = 1000, size: int = 1) -> list:
    t0 = at(start)
    return [(t0 + i * step_ms * MS, p, size) for i, p in enumerate(prices)]


def day_of(source, **kw) -> StrategyDay:
    kw = {"spawn": plain, "daily": [], "deadline_s": 0.3, **kw}
    return StrategyDay(rec(source), D, **kw)


@pytest.fixture
def days():
    """Every StrategyDay a test makes is killed at the end, whatever the test did."""
    made = []

    def make(source, **kw):
        made.append(day_of(source, **kw))
        return made[-1]
    yield make
    for d in made:
        d.kill()


# ---------------------------------------------------------------- the schedule
SCHEDULE = HEAD + '''class Sched(Strategy):
    id, name, root = "s", "Sched", "NQ"
    session_window = ("09:30", "10:00")
    bar_minutes = 5
    bar_window = ("09:30", "09:50")

    def times(self):
        return ["09:35:00", "09:30:00", "09:59", "10:00"]

    def on_session(self, ctx):
        self.n = 0
        self.say(ctx, "session", ctx.last_price or -1.0)

    def on_bar(self, ctx, bar):
        self.say(ctx, f"bar {bar.start_ns} {bar.end_ns} {bar.o} {bar.h} {bar.l} {bar.c}", float(bar.v))

    def on_time(self, ctx, et_time):
        self.say(ctx, f"time {et_time}", ctx.last_price or -1.0)

    def say(self, ctx, what, value):
        self.n += 1
        ctx.plot(f"{self.n} {what}", ctx.now_ns, value)
'''


def schedule_rows() -> list:
    rows = ticks("09:29:50", [99.0] * 5, 2000)                              # before the window: never seen
    rows += ticks("09:30:00", [100.0, 101.0, 99.5, 100.5], 60_000, size=3)   # the 09:30 bar
    rows += ticks("09:35:10", [102.0, 103.0], 1000, size=2)                  # the 09:35 bar; 09:40-09:45 has no print
    rows += ticks("09:45:30", [104.0], 1000)                                 # the 09:45 bar closes at 09:50
    rows += ticks("09:51:00", [105.0, 106.0], 240_000)                       # 09:51, 09:55
    rows += ticks("10:00:30", [107.0], 1000)                                 # after the window
    return rows


@pytest.mark.parametrize("batch", [1, 3, 200])
def test_the_events_come_in_the_testers_order_with_the_testers_bars(batch, days):
    rows = schedule_rows()
    want = run_session(cls_of(SCHEDULE)(), tape(rows), Costs()).plots
    day = days(SCHEDULE)
    for i in range(0, len(rows), batch):
        day.on_ticks(rows[i:i + batch])
        day.on_clock(rows[min(i + batch, len(rows)) - 1][0] // MS)
    assert day.state == "done"
    names = list(day.fills.result.plots)
    assert names == list(want) and day.fills.result.plots == want
    assert [n.split()[1] for n in names] == ["session", "time", "bar", "time", "bar", "bar", "time"]
    assert names[1].endswith("09:30:00") and names[3].endswith("09:35:00") and names[-1].endswith("09:59")
    assert not any("10:00" in n for n in names)                              # an event at the window's end never fires


# ---------------------------------------------------------------- the clock
MARKET_930 = HEAD + '''class M(Strategy):
    id, name, root = "m", "M", "NQ"

    def times(self):
        return ["09:30:00", "15:55"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
        else:
            ctx.flatten("time")
'''


def test_the_clock_fires_an_event_that_no_print_has_reached(days):
    day = days(MARKET_930)
    day.on_ticks(ticks("09:29:50", [21000.0] * 9))                           # the newest print is 09:29:58
    day.on_clock(ms_of("09:30:00", 500))
    assert day.state == "running" and day.summary()["orders"] == []         # half a second behind the clock: wait
    day.on_clock(ms_of("09:30:01", 1))
    assert day.summary()["orders"] == [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00", "refused": None}]
    day.on_ticks(ticks("09:30:02", [21001.0]))                               # the first print after the order went live
    day.on_clock(ms_of("15:55:01", 1))                                       # the flat, with no print at or after 15:55
    assert [o["text"] for o in day.summary()["orders"]][-1] == "Flatten (time)" and day.summary()["trades"] == []
    day.on_clock(ms_of("16:00:02"))
    assert day.state == "running"                                            # the end, and 2 s for prints on their way
    day.on_clock(ms_of("16:00:02", 1))
    s = day.summary()
    assert day.state == s["state"] == "done" and day.child_alive() is False
    assert s["trades"] == [{"side": "long", "qty": 1, "entry_t": "09:30:02", "entry_px": 21001.25, "exit_t": "09:30:02",
                            "exit_px": 21000.75, "reason": "eod", "net": -14.0}]
    assert s["net"] == -14.0


def test_a_day_made_after_its_window_is_run_from_the_prints_and_ends_done(days):
    day = days(MARKET_930)
    day.on_ticks(ticks("09:29:50", [21000.0] * 20) + ticks("15:54:59", [21010.0] * 3) + ticks("16:00:01", [21020.0]))
    assert day.state == "done" and day.child_alive() is False                # a print past the window's end ends it
    assert [t["reason"] for t in day.summary()["trades"]] == ["time"]


def test_a_print_still_on_its_way_at_the_end_of_the_window_is_not_dropped(days):
    """M3. The clock passes 16:00 before the last prints of the window arrive: they still count."""
    day = days(MARKET_930.replace('"15:55"', '"15:59:59"'))
    day.on_ticks(ticks("09:29:50", [21000.0] * 20) + ticks("15:59:50", [21010.0] * 5))     # up to 15:59:54
    day.on_clock(ms_of("16:00:01", 500))                                     # past the end; the flat fired by the clock
    assert day.state == "running" and day.summary()["trades"] == []
    day.on_ticks([(at("15:59:59", 800), 21030.0, 1)])                        # in transit when the clock passed 16:00
    (t,) = day.summary()["trades"]
    assert (t["exit_t"], t["exit_px"], t["reason"]) == ("15:59:59", 21029.75, "time") and day.state == "running"
    day.on_ticks([(at("16:00:00", 100), 21040.0, 1)])                        # a print at or after the end: the day is over
    assert day.state == "done" and len(day.summary()["trades"]) == 1


# ---------------------------------------------------------------- a strategy that must be stopped
def planted(body: str) -> str:
    return HEAD + f'''import os, sys, time


class P(Strategy):
    id, name, root = "p", "P", "NQ"

    def times(self):
        return ["09:30:00", "09:31:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
            return
{body}
'''


STOPS = {
    "raises": ('        raise RuntimeError("boom")', "Strategy error: boom"),
    "spins": ("        while True:\n            pass", "Too slow: no answer in 0.3 s."),
    "sleeps": ("        time.sleep(5)", "Too slow: no answer in 0.3 s."),
    "floods its stdout": ('        os.write(1, b"x" * 10_000_000)', "Too many orders at once."),
    "50 orders": ('        for _ in range(50):\n            ctx.market("long", sl=1.0, ref=2.0)',
                  "Too many orders at once."),
    "exits": ("        os._exit(0)", "The strategy stopped by itself."),
    "talks out of turn": ('        os.write(1, b"hello\\n")', "The strategy stopped by itself."),
}


@pytest.mark.parametrize("case", list(STOPS))
def test_a_broken_strategy_is_stopped_with_its_sentence_and_the_next_one_is_not_held_up(case, days):
    body, why = STOPS[case]
    bad, good = days(planted(body)), days(MARKET_930.replace('"09:30:00", "15:55"', '"09:31:00", "15:55"')
                                          .replace('et_time == "09:30:00"', 'et_time == "09:31:00"'))
    rows = ticks("09:29:50", [21000.0] * 80) + ticks("09:31:10", [21005.0] * 5)
    t = time.monotonic()
    for i in range(0, len(rows), 10):                                        # both fed in the same loop
        for d in (bad, good):
            d.on_ticks(rows[i:i + 10])
    took = time.monotonic() - t
    s = bad.summary()
    assert (bad.state, s["state"], s["why"]) == ("stopped", "stopped", why) and took < 2.0
    assert bad.child_alive() is False
    assert [o["text"] for o in s["orders"]] == ["Buy at market, stop 20,990.00"]     # nothing of the broken event
    (tr,) = s["trades"]                                                      # the open position: closed at the stop
    assert (tr["exit_t"], tr["exit_px"], tr["reason"]) == ("09:31:00", 20999.75, "strategy error")
    assert good.state == "running" and [o["t"] for o in good.summary()["orders"]] == ["09:31:00"]
    n = len(s["orders"])
    bad.on_ticks(ticks("09:32:00", [21000.0] * 3))                           # stopped for today: nothing more is sent
    bad.on_clock(ms_of("16:00"))
    assert bad.state == "stopped" and len(bad.summary()["orders"]) == n and len(bad.summary()["trades"]) == 1


def test_a_strategys_own_prints_are_harmless(days):
    day = days(planted('        print("x" * 10_000_000)\n        ctx.flatten("time")'))
    day.on_ticks(ticks("09:29:50", [21000.0] * 80) + ticks("09:31:10", [21005.0] * 5))
    assert day.state == "running" and day.summary()["orders"][-1]["text"] == "Flatten (time)"


@pytest.mark.parametrize("source, why", [
    (HEAD + "class Bad(Strategy:\n    pass\n", "Strategy error: invalid syntax (line 4)"),
    (HEAD + "x = 1\n", "Strategy error: a draft defines exactly one Strategy subclass (found 0)"),
    (HEAD + 'class W(Strategy):\n    id, name, root = "w", "W", "NQ"\n    session_window = ("nine", "ten")\n',
     "The strategy's settings cannot be read."),
    (HEAD + 'import nothing_like_this\n\n\nclass W(Strategy):\n    id, name, root = "w", "W", "NQ"\n',
     "Strategy error: No module named 'nothing_like_this'"),
    (HEAD + 'class W(Strategy):\n    id, name, root = "w", "W", "NQ"\n\n    def times(self):\n        raise KeyError()\n',
     "Strategy error."),
])
def test_a_strategy_that_does_not_start_is_stopped(source, why, days):
    day = days(source)
    assert day.state == "stopped" and day.summary()["why"].startswith(why) and day.child_alive() is False
    assert "Error" not in day.summary()["why"]                               # M9: no Python names for the owner
    day.on_ticks(ticks("09:29:50", [21000.0] * 80))
    day.on_clock(ms_of("16:00"))
    assert day.state == "stopped" and day.summary()["trades"] == []


def test_no_sandbox_no_strategy(days, monkeypatch):
    def refused(argv, run_dir):
        raise sandbox.SandboxUnavailable("no sandbox here")
    day = days(MARKET_930, spawn=refused)
    assert (day.state, day.summary()["why"]) == ("stopped", "The sandbox is not working.")
    monkeypatch.setattr(sandbox, "available", lambda: False)
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    day = StrategyDay(rec(MARKET_930), D, daily=[])                          # the default spawn: fail closed
    assert (day.state, day.summary()["why"]) == ("stopped", "The sandbox is not working.") and not started


DAILY = HEAD + '''class Dl(Strategy):
    id, name, root = "d", "Dl", "NQ"

    def needs_daily(self):
        return True

    def on_session(self, ctx):
        ctx.plot("days", ctx.now_ns, float(len(ctx.daily)))
        ctx.plot("last close", ctx.now_ns, ctx.daily[-1]["c"])
'''


def test_the_daily_bars_reach_the_session_event_only_when_the_strategy_needs_them(days):
    asked = []

    def daily(root, d):
        asked.append((root, d))
        return [{"date": "2024-03-01", "h": 3.0, "l": 1.0, "c": 2.0}, {"date": "2024-03-04", "h": 6.0, "l": 4.0, "c": 5.0}]

    day = days(DAILY, daily=daily)
    day.on_ticks(ticks("09:25:00", [21000.0]))
    assert asked == [("NQ", D)] and day.fills.result.plots == {"days": [[ms_of("09:25"), 2.0]],
                                                               "last close": [[ms_of("09:25"), 5.0]]}
    other = days(MARKET_930, daily=lambda root, d: asked.append("no"))       # it does not need them: never read
    assert other.state == "waiting" and len(asked) == 1

    def broken(root, d):
        raise OSError("disk")
    bad = days(DAILY, daily=broken)
    assert (bad.state, bad.summary()["why"]) == ("stopped", "The daily bars could not be read.")
    assert bad.child_alive() is False and bad.detail == "OSError: disk"


def test_an_event_that_breaks_in_the_runner_itself_stops_the_day(days, monkeypatch):
    """Not the strategy's fault, but a day that lost an event half way cannot be trusted: stop it and say so (M9: in
    plain words; what broke is kept for the journal)."""
    day = days(MARKET_930)
    monkeypatch.setattr(host.ShadowFills, "apply", lambda self, intents: 1 / 0)
    day.on_ticks(ticks("09:29:50", [21000.0] * 20))
    assert day.state == "stopped" and day.child_alive() is False
    assert day.summary()["why"] == "Stopped: the runner had a problem."
    assert day.detail == "ZeroDivisionError: division by zero"


def test_anything_that_breaks_while_a_day_starts_kills_its_child(days, monkeypatch):
    """M4. Not only the errors the start expects."""
    started = []

    def spawn(argv, run_dir):
        started.append(plain(argv, run_dir))
        return started[-1]

    def broken(root, d):
        raise RuntimeError("an error nobody planned for")
    day = days(DAILY, spawn=spawn, daily=broken)
    assert (day.state, day.summary()["why"]) == ("stopped", "Stopped: the runner had a problem.")
    assert day.detail == "RuntimeError: an error nobody planned for"
    assert len(started) == 1 and started[0].poll() is not None and day.child_alive() is False


@pytest.mark.parametrize("how", ["the spawn breaks", "the spawn hands back no pipes"])
def test_a_start_that_breaks_before_the_child_talks_leaves_no_child_and_no_folder(how, days, monkeypatch):
    made, started = [], []
    real = host.tempfile.mkdtemp
    monkeypatch.setattr(host.tempfile, "mkdtemp", lambda **kw: made.append(real(**kw)) or made[-1])

    def spawn(argv, run_dir):
        if how == "the spawn breaks":
            raise RuntimeError("no room")
        started.append(subprocess.Popen(argv, cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL))
        return started[-1]
    day = days(MARKET_930, spawn=spawn)
    assert (day.state, day.summary()["why"]) == ("stopped", "Stopped: the runner had a problem.")
    assert len(made) == 1 and not Path(made[0]).exists()
    for p in started:
        assert p.wait(timeout=5) is not None


# ---- I1: the child's settings (meta) are checked before anything is built from them
def meta_source(**attrs) -> str:
    body = "".join(f"    {k} = {v!r}\n" for k, v in attrs.items())
    return HEAD + 'class N(Strategy):\n    id, name, root = "n", "N", "NQ"\n' + body


BAD_META = {
    "bar_minutes below zero": meta_source(bar_minutes=-1),                   # the reviewer's: build_bars never came back
    "bar_minutes not a whole number": meta_source(bar_minutes=1.5),
    "bar_minutes a day and more": meta_source(bar_minutes=1441),
    "bar_minutes true": meta_source(bar_minutes=True),
    "a window that ends before it starts": meta_source(session_window=("16:00", "09:25")),
    "a window with seconds": meta_source(session_window=("09:25:00", "16:00")),
    "a window of three": meta_source(session_window=("09:25", "12:00", "16:00")),
    "a bar window that is empty": meta_source(bar_minutes=5, bar_window=("10:00", "10:00")),
    "a bar window of words": meta_source(bar_minutes=5, bar_window=("ten", "eleven")),
    "placement below zero": meta_source(placement_ms=-5),
    "placement of minutes": meta_source(placement_ms=60_001),
    "placement not a number": meta_source(placement_ms="85"),
    "times that are numbers": meta_source() + "\n    def times(self):\n        return [930, 1555]\n",
    "a time that is not one": meta_source() + '\n    def times(self):\n        return ["09:30", "25:00"]\n',
    "a time with a date": meta_source() + '\n    def times(self):\n        return ["2024-03-05T09:30"]\n',
    "too many times": meta_source() + '\n    def times(self):\n        return ["09:30"] * 501\n',
    "another market than the record's": meta_source().replace('"NQ"', '"ES"'),
}


@pytest.mark.parametrize("case", list(BAD_META))
def test_settings_that_cannot_be_read_stop_the_day_before_anything_is_built(case, days):
    t = time.monotonic()
    day = days(BAD_META[case])
    assert (day.state, day.summary()["why"]) == ("stopped", "The strategy's settings cannot be read.")
    assert day.child_alive() is False and day.fills is None
    day.on_ticks(ticks("09:29:50", [21000.0] * 200))                         # and the runner's thread comes back
    day.on_clock(ms_of("16:01"))
    assert day.state == "stopped" and time.monotonic() - t < 3.0


def test_settings_at_the_edges_are_read(days):
    day = days(meta_source(bar_minutes=1440, placement_ms=60_000, session_window=("00:00", "23:59"),
                           bar_window=("00:00", "23:59"))
               + '\n    def times(self):\n        return ["09:30", "09:30:15"] * 250\n')
    assert (day.state, day.summary()["why"]) == ("waiting", None)
    assert days(meta_source(bar_minutes=0, placement_ms=0)).state == "waiting"


def test_a_day_the_strategy_does_not_trade_is_not_today(days):
    day = days(HEAD + 'class N(Strategy):\n    id, name, root = "n", "N", "NQ"\n\n'
               '    def trades_on(self, d):\n        return d.weekday() == 4\n')
    assert day.state == "not_today" and day.child_alive() is False
    day.on_ticks(ticks("09:29:50", [21000.0] * 80))
    assert day.summary()["orders"] == []


@pytest.mark.skipif(not sandbox.available(), reason="the macOS sandbox is not working here")
def test_a_sandboxed_child_answers():
    rows = ticks("09:29:50", [21000.0] * 20) + ticks("15:54:59", [21010.0] * 3)
    got = run_day(rec(MARKET_930), rows, D)                                  # the default spawn: the sandbox
    assert got["summary"]["state"] == "done" and got["summary"]["why"] is None
    assert [(t["side"], t["exit_reason"]) for t in got["trades"]] == [("long", "time")]


# ---------------------------------------------------------------- prices late
def test_prices_late_is_said_while_it_lasts_and_reaches_the_door(days):
    """R1. Late = prints that ARRIVE more than 2 s behind the stream's clock, for 5 s running."""
    day = days(MARKET_930)
    day.on_clock(ms_of("09:29:55"))
    day.on_ticks(ticks("09:29:52", [21000.0]))                               # arrives 3 s behind the clock
    assert day.summary()["why"] is None
    day.on_clock(ms_of("09:29:59"))
    day.on_ticks(ticks("09:29:56", [21000.0]))                               # still 3 s behind, 4 s running
    assert day.summary()["why"] is None
    day.on_clock(ms_of("09:30:00", 500))
    day.on_ticks(ticks("09:29:57", [21000.0]))                               # 5.5 s running
    s = day.summary()
    assert (s["state"], s["why"]) == ("running", "Prices are late.")
    day.on_clock(ms_of("09:30:02"))                                          # 09:30:00 fires by the clock
    assert day.summary()["orders"] == [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00",
                                        "refused": "Prices are late."}]
    day.on_ticks(ticks("09:29:59", [21000.0]))                               # another late one: it lasts
    assert day.summary()["why"] == "Prices are late."
    day.on_ticks(ticks("09:30:01", [21001.0]))                               # one that arrives within 2 s of the clock
    assert day.summary()["why"] is None
    assert not day.fills.flat                                                # shadow: the refused order still filled


def test_a_market_with_no_prints_is_quiet_not_late(days):
    day = days(MARKET_930)
    day.on_ticks(ticks("09:29:50", [21000.0] * 5))                           # then nothing for a minute
    for s in range(55, 60):
        day.on_clock(ms_of(f"09:29:{s}"))
    for s in range(0, 40, 3):
        day.on_clock(ms_of(f"09:30:{s:02d}"))
        assert day.summary()["why"] is None
    assert day.summary()["orders"] == [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00", "refused": None}]
    day.on_ticks(ticks("09:30:30", [21000.0]))                               # and one late print alone is not "late"
    assert day.summary()["why"] is None


def test_no_clock_from_the_stream_is_said_and_reaches_the_door(days):
    day = days(MARKET_930)
    day.on_ticks(ticks("09:29:50", [21000.0] * 5))
    day.on_clock(ms_of("09:29:55"))
    day.no_prices(True)                                                      # the runner: no clock for 5 s
    s = day.summary()
    assert (s["state"], s["why"]) == ("running", "No prices: the chart service is not answering.")
    day.on_ticks(ticks("09:29:55", [21000.0] * 8))                           # the stream is back with what was missed:
    assert day.summary()["orders"][0]["refused"] == "Prices are late."       # those orders could not have gone out
    assert day.summary()["why"] == "No prices: the chart service is not answering."
    day.no_prices(False)                                                     # its clock resumes
    assert day.summary()["why"] is None


# ---------------------------------------------------------------- the summary
STRADDLE = HEAD + '''class S(Strategy):
    id, name, root = "s", "S", "NQ"

    def times(self):
        return ["09:30:00", "09:40", "09:50", "15:55"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            px = ctx.last_price
            ctx.move_brackets_to_fill = True
            self.up = ctx.stop_entry("long", px + 50.25, sl=px + 0.25, tp=px + 150.25)
            self.dn = ctx.stop_entry("short", px - 50, sl=px, tp_rr=2)
            ctx.oco(self.up, self.dn)
        elif et_time == "09:40":
            ctx.cancel(self.dn)
            ctx.market("short", sl=ctx.last_price + 80)
            ctx.market("long")
            ctx.stop_entry("long", ctx.last_price + 5, sl=ctx.last_price, qty=3)
        elif et_time == "09:50":
            ctx.limit_entry("long", ctx.last_price - 5, sl=ctx.last_price - 9)
            ctx.cancel(self.up)
        else:
            ctx.flatten("time")
'''


def test_the_summary_reads_in_plain_words(days):
    saved, wall = [], [100.0]
    day = days(STRADDLE, save=saved.append, wall=lambda: wall[0])
    assert [s["state"] for s in saved] == ["waiting"]
    day.on_ticks(ticks("09:29:50", [21400.0] * 9) + ticks("09:30:01", [21400.0] * 3))
    day.on_ticks(ticks("09:39:58", [21400.0] * 4))
    day.on_ticks(ticks("09:49:58", [21400.0] * 4) + ticks("15:54:58", [21400.0] * 4) + ticks("16:00:00", [21400.0]))
    day.on_clock(ms_of("16:00"))
    s = day.summary()
    assert s["orders"] == [
        {"t": "09:30:00", "text": "Buy stop 21,450.25, stop 21,400.25, target 21,550.25", "refused": None},
        {"t": "09:30:00", "text": "Sell stop 21,350.00, stop 21,400.00, target 2 x the stop", "refused": None},
        {"t": "09:30:00", "text": "One cancels the other", "refused": None},
        {"t": "09:40:00", "text": "Cancel", "refused": None},
        {"t": "09:40:00", "text": "Sell at market, stop 21,480.00", "refused": "One position at a time."},
        {"t": "09:40:00", "text": "Buy at market", "refused": "Every entry needs a stop held at the broker."},
        {"t": "09:40:00", "text": "Buy stop 21,405.00, stop 21,400.00", "refused": "Size is set on the Desk, per account."},
        {"t": "09:50:00", "text": "Buy limit 21,395.00, stop 21,391.00", "refused": "Limit entries are not built yet."},
        {"t": "09:50:00", "text": "Cancel", "refused": None},
        {"t": "15:55:00", "text": "Flatten (time)", "refused": None}]
    assert set(s) == {"date", "sha256", "state", "why", "orders", "trades", "net", "match", "updated_utc"}
    assert (s["date"], s["sha256"], s["state"], s["why"], s["match"]) == ("2024-03-05", rec(STRADDLE)["sha256"], "done",
                                                                           None, None)
    assert dt.datetime.fromisoformat(s["updated_utc"]).tzinfo is not None
    assert [set(t) for t in s["trades"]] == [{"side", "qty", "entry_t", "entry_px", "exit_t", "exit_px", "reason", "net"}] * 2
    assert sorted((t["side"], t["entry_t"], t["exit_t"], t["reason"]) for t in s["trades"]) == [
        ("long", "09:40:01", "15:55:00", "time"), ("short", "09:40:01", "15:55:00", "time")]   # shadow: refused orders fill too
    assert s["net"] == round(sum(t["net"] for t in s["trades"]), 2)
    assert json.loads(json.dumps(s)) == s
    # the save callback: every state change at once, anything else at most once a second
    assert [x["state"] for x in saved] == ["waiting", "running", "done"] and saved[-1] == s


def test_a_day_that_is_killed_saves_its_summary_first(days):
    """M6. The runner going away, or a fresh day taking this one's place: what is known is written."""
    saved = []
    day = days(STRADDLE, save=saved.append, wall=lambda: 100.0)
    day.on_ticks(ticks("09:29:50", [21400.0] * 9) + ticks("09:30:01", [21400.0] * 3))
    day.on_ticks(ticks("09:39:58", [21400.0] * 4))                           # four more orders, inside the second
    assert len(saved[-1]["orders"]) == 3
    day.kill()
    assert len(saved[-1]["orders"]) == 7 and saved[-1]["state"] == "running" and day.child_alive() is False
    n = len(saved)
    day.kill()
    assert len(saved) == n


def test_the_summary_is_saved_at_most_once_a_second_between_state_changes(days):
    saved, wall = [], [100.0]
    day = days(STRADDLE, save=saved.append, wall=lambda: wall[0])
    day.on_ticks(ticks("09:29:50", [21400.0] * 9) + ticks("09:30:01", [21400.0] * 3))
    assert [(x["state"], len(x["orders"])) for x in saved] == [("waiting", 0), ("running", 3)]
    day.on_ticks(ticks("09:39:58", [21400.0] * 4))                           # four more orders, inside the second
    assert len(saved) == 2
    wall[0] += 0.5
    day.on_clock(ms_of("09:40:02"))
    assert len(saved) == 2
    wall[0] += 0.6
    day.on_clock(ms_of("09:40:03"))                                          # nothing new happened, the second is over
    assert [(x["state"], len(x["orders"])) for x in saved][2:] == [("running", 7)]
    day.on_clock(ms_of("09:40:04"))
    assert len(saved) == 3                                                   # nothing changed: nothing is written


# ---------------------------------------------------------------- the runner
MON, WED = dt.date(2024, 3, 4), dt.date(2024, 3, 6)
NO_STREAM = "No prices: the chart service is not answering."
TOO_LATE = "Started too late to follow today."


class Desk:
    """A Runner on a temp store, fed by hand: what the tick client and the main loop would hand it. It starts as a
    connection that has caught up (`live`), unless told otherwise."""

    def __init__(self, tmp_path, live=True, **kw):
        self.at = tmp_path / "desklab"
        self.wall = [1000.0]                         # the runner's wall clock, moved by hand
        self.last_clock = None
        self.spawned: list = []
        kw.setdefault("daily", lambda root, d: [])
        self.r = Runner(at=self.at, source="http://127.0.0.1:8852", spawn=self.spawn, deadline_s=0.3,
                        wall=lambda: self.wall[0], **kw)
        if live:
            self.r.take(("live",))

    def spawn(self, argv, run_dir):
        self.spawned.append(plain(argv, run_dir))
        return self.spawned[-1]

    def promote(self, source=MARKET_930, name="lab_x", **kw):
        return store.put(rec(source, name, **kw), self.at)

    def clock(self, hms, d=D, ms=0):
        self.last_clock = ms_of(hms, ms, d)
        self.r.on_clock(self.last_clock)

    def rows(self, start, prices, d=D, root="NQ", step_ms=1000):
        t0 = ms_of(start, d=d)
        self.r.on_rows(root, [[t0 + i * step_ms, p, 1] for i, p in enumerate(prices)])

    def open(self, d=D, root="NQ", px=21000.0):
        """The session's first print: 18:00:05 the evening before (a tape that holds the whole session)."""
        self.rows("18:00:05", [px], d - dt.timedelta(days=1), root)

    def file(self, name="lab_x", d=D):
        return store.get_day(name, d.isoformat(), self.at)

    def today(self, name="lab_x", d=D):
        """The day file, once the second a summary may wait to be written is over (the stream's next clock)."""
        self.wall[0] += 1.5
        if self.last_clock is not None:
            self.r.on_clock(self.last_clock)
        return self.file(name, d)

    def journal(self, name="lab_x"):
        f = self.at / name / "journal.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.is_file() else []


@pytest.fixture
def desk(tmp_path):
    made = []

    def make(**kw):
        made.append(Desk(tmp_path, **kw))
        return made[-1]
    yield make
    for d in made:
        d.r.close()
        assert not [p for p in d.spawned if p.poll() is None]                # no child outlives its runner


def test_a_promoted_strategy_is_hosted_fed_and_written_down(desk):
    k = desk()
    k.promote()
    k.clock("09:29:00")
    k.r.sync()
    assert k.r.hosting() == [] and k.r.roots() == ["NQ"] and k.today() is None    # no print for its market yet
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    assert k.r.hosting() == ["lab_x"] and k.today()["state"] == "running"         # the session began at 09:25
    k.rows("09:30:00", [21000.0, 21001.0])
    k.clock("09:30:02")
    s = k.today()
    assert s["orders"] == [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00", "refused": None}]
    lines = k.journal()
    assert [(x["kind"], x["date"], x["t"], x["text"]) for x in lines] == [
        ("order", "2024-03-05", "09:30:00", "Buy at market, stop 20,990.00")]
    k.rows("15:54:59", [21010.0] * 3)
    k.clock("16:00:03")
    assert k.today()["state"] == "done" and k.r.hosting() == []
    assert [x["kind"] for x in k.journal()] == ["order", "order", "trade"]
    assert k.journal()[-1]["reason"] == "time" and k.journal()[-1]["net"] == k.today()["net"]
    k.r.sync()
    assert k.today()["state"] == "done" and len(k.spawned) == 1              # a finished day is not started again


def test_a_strategy_that_appears_late_is_caught_up_from_todays_prints_with_no_journal(desk):
    k = desk()
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.rows("09:30:00", [21000.0, 21001.0])
    k.clock("09:31:00")
    k.promote()
    k.r.sync()
    s = k.today()
    assert s["state"] == "running" and [o["t"] for o in s["orders"]] == ["09:30:00"] and k.journal() == []
    k.rows("15:54:59", [21010.0] * 3)                                        # live from here on
    assert [(x["kind"], x.get("text")) for x in k.journal()] == [("order", "Flatten (time)"), ("trade", None)]


def test_a_stop_is_journaled_once(desk):
    k = desk()
    body, why = STOPS["raises"]
    k.promote(planted(body))
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    k.rows("09:30:00", [21000.0] * 80)
    k.clock("09:32:00")
    k.r.sync()
    assert (k.today()["state"], k.today()["why"]) == ("stopped", why)
    assert [x["kind"] for x in k.journal()] == ["order", "stop", "trade"]
    assert (k.journal()[1]["why"], k.journal()[1]["detail"]) == (why, "RuntimeError: boom")    # M9: the detail is here


def test_switched_off_or_removed_its_child_is_stopped_and_the_day_reads_off(desk):
    k = desk()
    k.promote()
    k.promote(name="lab_y")
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    a, b = k.r.day("lab_x"), k.r.day("lab_y")
    assert a.child_alive() and b.child_alive()
    store.set_enabled("lab_x", False, k.at)
    store.remove("lab_y", k.at)
    k.r.sync()
    assert k.r.hosting() == [] and not a.child_alive() and not b.child_alive()
    assert k.today("lab_x")["state"] == k.today("lab_y")["state"] == "off"
    store.set_enabled("lab_x", True, k.at)                                   # switched on: a fresh day
    k.r.sync()
    assert k.r.hosting() == ["lab_x"] and k.today("lab_x")["state"] == "running" and k.r.day("lab_x") is not a


def test_changed_code_gets_a_fresh_day_and_the_old_one_is_saved_first(desk):
    k = desk()
    k.promote()
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    old = k.r.day("lab_x")
    k.rows("09:30:00", [21000.0, 21001.0])                                   # an order the day file has not seen yet
    assert k.file()["orders"] == []
    newer = MARKET_930.replace("- 10", "- 20")
    k.promote(newer)
    saved = []
    old._save = lambda s, was=old._save: (saved.append(s), was(s))
    k.r.sync()
    assert [len(x["orders"]) for x in saved] == [1]                          # M6: the old day's last word, then the new
    assert not old.child_alive() and k.r.day("lab_x") is not old
    s = k.today()
    assert s["sha256"] == rec(newer)["sha256"] and [o["text"] for o in s["orders"]] == ["Buy at market, stop 20,980.00"]


def test_when_the_session_rolls_every_day_is_finished_and_new_days_start(desk):
    """C2. The runner's day is the SESSION date of the stream's clock (it rolls at 18:00 ET, as the chart service's
    tape and the tester's do), not the calendar date."""
    k = desk()
    k.promote()
    k.clock("09:00:00", MON)
    k.open(MON)
    k.rows("09:29:50", [21000.0] * 9, MON)
    k.rows("09:30:00", [21000.0, 21001.0], MON)
    k.r.sync()
    old = k.r.day("lab_x")
    assert k.r.date("NQ") == MON
    k.rows("15:54:59", [21050.0] * 3, MON)
    k.clock("17:59:59", MON)
    assert k.r.day("lab_x") is old and k.r.date("NQ") == MON and k.file(d=MON)["state"] == "done"
    k.rows("18:00:00", [21052.0], MON)                                       # the next session's first print, before its clock
    before = (k.at / "lab_x" / "days" / f"{MON}.json").read_bytes()
    k.clock("18:00:01", MON)
    assert k.r.date("NQ") == D and not old.child_alive() and k.r.prints("NQ") == 1     # Monday's prints are dropped
    assert (k.at / "lab_x" / "days" / f"{MON}.json").read_bytes() == before  # nothing fires, Monday's file stays
    assert k.r.day("lab_x") is not old and k.file(d=D)["state"] == "waiting" and k.r.hosting() == ["lab_x"]
    k.clock("23:59:59", MON)
    k.clock("00:00:01", D)                                                   # midnight changes nothing
    assert k.r.date("NQ") == D and k.file(d=D)["state"] == "waiting" and len(k.spawned) == 2


def test_a_day_still_open_when_the_session_rolls_is_finished_as_the_tester_would(desk):
    late = MARKET_930.replace('session_window = ("09:25", "16:00")', "").replace(
        'id, name, root = "m", "M", "NQ"', 'id, name, root = "m", "M", "NQ"\n    session_window = ("09:25", "23:00")')
    k = desk()
    k.promote(late)
    k.clock("09:00:00", MON)
    k.open(MON)
    k.rows("09:29:50", [21000.0] * 9, MON)
    k.rows("09:30:00", [21000.0, 21001.0], MON)
    k.r.sync()
    k.clock("17:59:59", MON)
    assert k.file(d=MON)["state"] == "running"
    k.clock("18:00:01", MON)
    s = k.file(d=MON)
    assert s["state"] == "done" and [t["reason"] for t in s["trades"]] == ["eod"]


def test_a_weekend_session_is_never_hosted(desk):
    k = desk()
    k.promote()
    k.promote(name="coin", root="BTC")
    sat = dt.date(2024, 3, 9)
    k.clock("09:00:00", sat)
    k.rows("08:00:00", [60000.0] * 5, sat, root="BTC")                       # a 24/7 market has a Saturday session
    k.r.sync()
    assert k.r.date("BTC") == sat and k.r.prints("BTC") == 5
    assert k.r.date("NQ") == dt.date(2024, 3, 11)                            # for the others it is Monday's, not begun
    assert k.r.hosting() == [] and k.spawned == [] and k.file("coin", sat) is None


def test_the_heartbeat_says_who_is_hosted_and_how_old_the_prices_are(desk):
    k = desk()
    k.promote()
    k.promote(name="es_one", root="ES")
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.clock("09:29:59")
    k.r.sync()
    k.r.beat()
    b = store.get_runner(k.at)
    assert set(b) == {"pid", "seen_utc", "source", "prices", "hosting"} and b["source"] == "http://127.0.0.1:8852"
    assert b["hosting"] == ["lab_x"] and b["prices"] == {"ES": {"age_s": None, "late": False},     # quiet, not late
                                                         "NQ": {"age_s": 1.0, "late": False}}
    assert abs((dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(b["seen_utc"])).total_seconds()) < 5
    for clock, print_ in (("09:30:02", "09:29:59"), ("09:30:05", "09:30:02"), ("09:30:08", "09:30:05")):
        k.clock(clock)                                                       # R1: prints that ARRIVE 3 s behind the clock,
        k.rows(print_, [21000.0])                                            # 5 s running
    k.r.beat()
    assert store.get_runner(k.at)["prices"]["NQ"] == {"age_s": 3.0, "late": True}
    for s in ("09:30:20", "09:30:40"):                                       # then nothing at all: quiet, still as it was
        k.clock(s)
    k.r.beat()
    assert store.get_runner(k.at)["prices"]["NQ"] == {"age_s": 35.0, "late": True}
    k.rows("09:30:40", [21000.0])                                            # a print that arrives on time
    k.r.beat()
    assert store.get_runner(k.at)["prices"]["NQ"] == {"age_s": 0.0, "late": False}


def test_no_clock_from_the_stream_for_five_seconds_is_no_prices(desk):
    k = desk()
    k.promote()
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.clock("09:29:59")
    k.r.sync()
    k.wall[0] += 4.9
    k.r.idle()
    assert k.file()["why"] is None
    k.wall[0] += 0.2                                                         # 5 s by the runner's own time
    k.r.idle()
    k.r.beat()
    assert (k.file()["state"], k.file()["why"]) == ("running", NO_STREAM)
    assert store.get_runner(k.at)["prices"] == {"NQ": {"age_s": None, "late": True}}
    k.r.take(("connect",))                                                   # back: first what was missed ...
    k.rows("09:29:59", [21000.0] * 4)
    assert k.r.day("lab_x").summary()["orders"][0]["refused"] == "Prices are late."
    assert k.r.day("lab_x").summary()["why"] == NO_STREAM
    k.r.take(("live",))
    k.clock("09:30:03")                                                      # ... then its clock: the prices are back
    assert k.today()["why"] is None
    k.r.beat()
    assert store.get_runner(k.at)["prices"] == {"NQ": {"age_s": 1.0, "late": False}}


def test_a_stuck_strategy_does_not_hold_up_another_in_the_runner(desk):
    k = desk()
    k.promote(planted(STOPS["spins"][0]), name="lab_bad")
    k.promote(MARKET_930.replace('"09:30:00", "15:55"', '"09:31:00", "15:55"')
              .replace('et_time == "09:30:00"', 'et_time == "09:31:00"'), name="lab_good")
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    t = time.monotonic()
    k.rows("09:30:00", [21000.0] * 80)
    k.clock("09:31:21")
    assert time.monotonic() - t < 2.0
    assert k.today("lab_bad")["why"] == "Too slow: no answer in 0.3 s."
    assert [o["t"] for o in k.today("lab_good")["orders"]] == ["09:31:00"]


# ---- C1: a clock never runs ahead of the backlog
def a_930_day(k: Desk, reconnect: bool):
    """The reviewer's case: the connection is away 09:29:58 .. 09:30:03 and comes back with what it missed."""
    k.promote()
    k.clock("09:29:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 8)                                        # 09:29:50 .. 09:29:57
    k.r.sync()

    def missed():
        k.rows("09:29:58", [21010.0, 21020.0])
        k.rows("09:30:00", [21020.0, 21021.0])
    if reconnect:
        k.r.take(("connect",))
        k.r.on_clock(ms_of("09:30:03"))                                      # a clock ahead of its backlog (an old service)
        missed()                                                             # the backlog
        k.r.take(("live",))
        k.clock("09:30:03")
    else:
        missed()
        k.clock("09:30:03")
    k.rows("15:54:59", [21030.0] * 3)
    k.clock("16:00:03")
    s = k.today()
    return [o["text"] for o in s["orders"]], [(t["entry_px"], t["exit_px"], t["reason"], t["net"]) for t in s["trades"]]


def test_a_reconnect_gives_the_day_the_prints_in_order_would(tmp_path):
    days = []
    for sub, reconnect in (("a", False), ("b", True)):
        k = Desk(tmp_path / sub)
        try:
            days.append(a_930_day(k, reconnect))
        finally:
            k.r.close()
    assert days[0] == days[1] == (["Buy at market, stop 21,010.00", "Flatten (time)"],
                                  [(21021.25, 21029.75, "time", 166.0)])


def test_nothing_is_hosted_while_a_backlog_is_in_flight(desk):
    k = desk(live=False)
    k.promote()
    k.r.sync()
    k.r.take(("connect",))
    k.r.on_clock(ms_of("09:31:00"))                                          # even with a clock
    k.open()
    k.rows("09:29:50", [21000.0] * 9)                                        # half of the backlog
    k.r.sync()
    assert k.r.hosting() == [] and k.spawned == [] and k.file() is None and k.r.date("NQ") is None
    k.rows("09:30:00", [21000.0, 21001.0])                                   # the rest
    k.r.take(("live",))
    k.r.sync()
    assert k.r.hosting() == [] and k.spawned == []                           # no clock yet: no date to host on
    k.clock("09:31:00")
    k.r.sync()
    assert k.r.hosting() == ["lab_x"] and [o["t"] for o in k.today()["orders"]] == ["09:30:00"]


# ---- C2: the session date, and never an empty day over a finished one
FINISHED = {"date": D.isoformat(), "sha256": "x", "state": "done", "why": None,
            "orders": [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00", "refused": None}],
            "trades": [{"side": "long", "net": 180.0}], "net": 180.0, "match": None, "updated_utc": "x"}


@pytest.mark.parametrize("clock_first", [False, True])
def test_a_start_in_the_evening_leaves_the_finished_day_exactly_as_it_is(desk, clock_first):
    """The reviewer's 19:00 case. The stream's backlog is the session that began at 18:00: tomorrow's."""
    k = desk(live=clock_first)
    k.promote()
    store.put_day("lab_x", FINISHED, k.at)
    f = k.at / "lab_x" / "days" / f"{D}.json"
    before = f.read_bytes()
    k.r.sync()
    if clock_first:                                                          # as the reviewer ran it
        k.clock("19:00:00")
        k.rows("18:00:01", [21100.0] * 5)
    else:                                                                    # as the stream sends it now
        k.r.take(("connect",))
        k.rows("18:00:01", [21100.0] * 5)
        k.r.take(("live",))
        k.clock("19:00:00")
    k.r.sync()
    assert f.read_bytes() == before
    assert k.r.date("NQ") == WED and k.r.hosting() == ["lab_x"] and k.file(d=WED)["state"] == "waiting"
    k.clock("19:00:05")
    k.r.sync()
    assert f.read_bytes() == before and sorted(p.name for p in f.parent.iterdir()) == [f"{D}.json", f"{WED}.json"]


def test_a_start_before_the_roll_rebuilds_the_same_finished_day(desk):
    """17:30 ET: the stream still holds the whole session, so the day can be made again in full."""
    def session(k):
        k.open()
        k.rows("09:29:50", [21000.0] * 9)
        k.rows("09:30:00", [21000.0, 21001.0])
        k.rows("15:54:59", [21010.0] * 3)
        k.rows("16:59:58", [21015.0] * 2)

    k = desk()
    k.promote()
    k.clock("08:00:00")
    session(k)
    k.r.sync()                                                               # (hosted late in the day: all catch-up)
    k.clock("17:00:00")
    first = k.today()
    assert first["state"] == "done" and len(first["orders"]) == 2 and [t["reason"] for t in first["trades"]] == ["time"]
    k.r.close()
    again = desk(live=False)                                                 # the runner starts again
    again.r.sync()
    again.r.take(("connect",))
    session(again)
    again.r.take(("live",))
    again.clock("17:30:00")
    again.r.sync()
    second = again.today()
    assert again.r.date("NQ") == D and {**second, "updated_utc": None} == {**first, "updated_utc": None}


def test_a_day_that_cannot_be_rebuilt_in_full_is_not_hosted(desk):
    """Fail closed: the clock is past the window's start and the tape held begins after it."""
    k = desk()
    k.promote()
    k.promote(name="lab_y")
    store.put_day("lab_y", FINISHED, k.at)
    f = k.at / "lab_y" / "days" / f"{D}.json"
    before = f.read_bytes()
    k.clock("10:00:00")
    k.rows("09:40:00", [21000.0] * 5)                                        # the oldest print held; the window began 09:25
    k.r.sync()
    assert k.r.hosting() == [] and not [p for p in k.spawned if p.poll() is None]
    s = k.file("lab_x")
    assert (s["state"], s["why"], s["orders"], s["trades"]) == ("stopped", TOO_LATE, [], [])
    assert f.read_bytes() == before                                          # a day file that exists is left as it is
    n = len(k.spawned)
    k.rows("09:40:05", [21000.0] * 5)
    k.clock("10:00:05")
    k.r.sync()
    k.r.close()                                                              # (kill saves: not over that file either)
    assert len(k.spawned) == n and f.read_bytes() == before and k.journal("lab_y") == []


def test_a_window_that_has_not_begun_is_hosted_whenever_the_tape_starts(desk):
    k = desk()
    k.promote()
    k.clock("09:20:00")
    k.rows("09:19:58", [21000.0] * 2)
    k.r.sync()
    assert k.r.hosting() == ["lab_x"] and k.file()["state"] == "waiting"


# ---- M4 / M5 at the runner
def test_a_day_that_breaks_at_its_start_is_not_tried_again_and_leaves_no_child(desk):
    def broken(root, d):
        raise RuntimeError("an error nobody planned for")
    k = desk(daily=broken)
    k.promote(DAILY)
    k.clock("09:00:00")
    k.open()
    for _ in range(3):
        k.r.sync()
    assert len(k.spawned) == 1 and k.spawned[0].poll() is not None and k.r.hosting() == []
    assert k.file()["why"] == "Stopped: the runner had a problem."
    assert [(x["kind"], x["why"], x["detail"]) for x in k.journal()] == [
        ("stop", "Stopped: the runner had a problem.", "RuntimeError: an error nobody planned for")]


def test_a_roll_to_an_earlier_day_drops_the_prints_held(desk):
    """M5. A replayed session takes the stream's place: nothing of the later day may be left under it."""
    k = desk()
    k.promote()
    k.clock("09:00:00")
    k.open()
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    old = k.r.day("lab_x")
    k.r.take(("connect",))
    k.open(MON, px=20000.0)
    k.rows("09:29:50", [20000.0] * 9, MON)
    k.r.take(("live",))
    k.clock("09:30:00", MON)
    assert k.r.date("NQ") == MON and k.r.prints("NQ") == 10 and not old.child_alive()
    assert k.r.day("lab_x") is not old and k.file(d=MON)["state"] == "running"
    k.clock("09:30:02", MON)
    assert k.today(d=MON)["orders"] == [{"t": "09:30:00", "text": "Buy at market, stop 19,990.00", "refused": None}]


# ---------------------------------------------------------------- the tick client
def client(handler, roots=("NQ",), **kw):
    got, slept = [], []
    c = TickClient("http://127.0.0.1:8852", lambda: list(roots), got.append, transport=httpx.MockTransport(handler),
                   sleep=slept.append, **kw)
    return c, got, slept


def sse(*events) -> bytes:
    out = b""
    for name, data in events:
        out += (f"event: {name}\n" if name else "").encode() + f"data: {json.dumps(data)}\n\n".encode()
    return out


def test_no_print_is_taken_twice():
    c, _, _ = client(lambda req: httpx.Response(500))
    assert c.fresh("NQ", [[10, 1.0, 1], [11, 2.0, 1], [11, 3.0, 1]]) == [[10, 1.0, 1], [11, 2.0, 1], [11, 3.0, 1]]
    assert c.fresh("NQ", [[11, 4.0, 1], [9, 0.0, 1]]) == [[11, 4.0, 1]]      # the same connection: a new print at 11
    c.reconnected()
    # the stream starts again from 10: older rows go, and of the rows AT 11 the first three (the ones held) go
    again = [[10, 1.0, 1], [11, 2.0, 1], [11, 3.0, 1], [11, 4.0, 1], [11, 5.0, 1], [12, 6.0, 1]]
    assert c.fresh("NQ", again) == [[11, 5.0, 1], [12, 6.0, 1]]
    assert c.fresh("NQ", [[12, 7.0, 1]]) == [[12, 7.0, 1]]
    assert c.fresh("ES", [[5, 1.0, 1]]) == [[5, 1.0, 1]]                     # each market by itself


def test_the_client_asks_for_the_whole_session_then_from_its_oldest_newest_print_and_backs_off():
    asked = []
    bodies = [sse((None, {"root": "NQ", "rows": [[100, 1.0, 1], [200, 2.0, 2]]}),
                  (None, {"root": "ES", "rows": [[150, 5.0, 1]]}), ("live", {}), ("clock", {"now_ms": ms_of("10:00")})),
              None, None,
              sse((None, {"root": "NQ", "rows": [[200, 2.0, 2], [200, 2.5, 1], [300, 3.0, 1]]}),
                  (None, {"root": "ES", "rows": [[150, 5.0, 1], [160, 6.0, 1]]}), ("live", {}),
                  ("clock", {"now_ms": ms_of("10:00", 5)})),
              None]
    stop = host.threading.Event()

    def handler(req):
        asked.append(dict(req.url.params))
        assert req.url.host == "127.0.0.1" and req.url.path == "/api/labrun/ticks" and "origin" not in req.headers
        body = bodies[len(asked) - 1]
        if len(asked) == len(bodies):
            stop.set()
        if body is None:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    c, got, slept = client(handler, roots=("NQ", "ES"))
    c.run(stop)
    assert asked == ([{"roots": "NQ,ES", "since_ms": "0"}] + [{"roots": "NQ,ES", "since_ms": "150"}] * 3   # C2: the whole
                     + [{"roots": "NQ,ES", "since_ms": "160"}])                                           # session first
    assert got == [("connect",), ("ticks", "NQ", [[100, 1.0, 1], [200, 2.0, 2]]), ("ticks", "ES", [[150, 5.0, 1]]),
                   ("live",), ("clock", ms_of("10:00")),
                   ("connect",), ("ticks", "NQ", [[200, 2.5, 1], [300, 3.0, 1]]), ("ticks", "ES", [[160, 6.0, 1]]),
                   ("live",), ("clock", ms_of("10:00", 5))]
    assert slept == [1.0, 1.0, 2.0, 1.0]                                     # 1 s after a stream that worked, then doubling


def test_the_back_off_grows_to_thirty_seconds():
    stop = host.threading.Event()
    n = [0]

    def handler(req):
        n[0] += 1
        if n[0] == 8:
            stop.set()
        return httpx.Response(503)

    c, got, slept = client(handler)
    c.run(stop)
    assert slept == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0] and got == []     # no stream: nothing is handed on


def test_a_stream_whose_clock_goes_back_is_another_timeline_and_is_asked_again_whole():
    """A replayed session takes the live service's place: what is held from the later day says nothing about it."""
    asked = []
    stop = host.threading.Event()
    live, replayed = ms_of("10:00"), ms_of("09:40", d=MON)
    bodies = [sse((None, {"root": "NQ", "rows": [[live - 5, 9.0, 1]]}), ("live", {}), ("clock", {"now_ms": live})),
              sse((None, {"root": "NQ", "rows": [[replayed - 5, 1.0, 1]]}), ("live", {}), ("clock", {"now_ms": replayed})),
              sse((None, {"root": "NQ", "rows": [[replayed - 5, 1.0, 1]]}), ("live", {}), ("clock", {"now_ms": replayed})),
              sse()]

    def handler(req):
        asked.append(int(req.url.params["since_ms"]))
        if len(asked) == len(bodies):
            stop.set()
        return httpx.Response(200, content=bodies[len(asked) - 1])

    c, got, slept = client(handler)
    c.run(stop)
    assert asked == [0, live - 5, 0, replayed - 5] and slept == [1.0, 1.0]   # the third: at once
    assert [x for x in got if x[0] == "ticks"] == [("ticks", "NQ", [[live - 5, 9.0, 1]]),
                                                   ("ticks", "NQ", [[replayed - 5, 1.0, 1]])]
    assert [x for x in got if x[0] == "clock"] == [("clock", live), ("clock", replayed)]


def test_a_surprise_in_the_stream_never_ends_the_reader():
    """Whatever a line holds, the reader's thread logs it, backs off and asks again."""
    stop = host.threading.Event()
    bodies = [b"data: [1, 2]\n\n", b"data: {\"root\": \"NQ\"}\n\n", b"data: not json\n\n",
              sse((None, {"root": "NQ", "rows": [[5, 1.0, 1]]}))]
    n = [0]

    def handler(req):
        n[0] += 1
        if n[0] > len(bodies):
            stop.set()
            return httpx.Response(503)
        return httpx.Response(200, content=bodies[n[0] - 1])

    c, got, slept = client(handler)
    c.run(stop)
    assert [x for x in got if x[0] == "ticks"] == [("ticks", "NQ", [[5, 1.0, 1]])] and slept == [1.0, 2.0, 4.0, 1.0]


def test_the_client_reconnects_when_the_markets_it_wants_change():
    asked, roots = [], ["NQ"]
    stop = host.threading.Event()

    def handler(req):
        asked.append(req.url.params["roots"])
        roots[:] = ["NQ", "ES"]
        if len(asked) == 2:
            stop.set()
        return httpx.Response(200, content=sse(("clock", {"now_ms": ms_of("10:00")}), ("clock", {"now_ms": ms_of("10:00")})))

    slept = []
    c = TickClient("http://127.0.0.1:8852", lambda: list(roots), lambda item: None,
                   transport=httpx.MockTransport(handler), sleep=slept.append)
    c.run(stop)
    assert asked == ["NQ", "NQ,ES"] and slept == []                          # at once: no back-off


# ---------------------------------------------------------------- python -m homebase.labrun
@pytest.mark.parametrize("url", ["http://10.0.0.5:8852", "http://example.com:8852", "https://localhost.evil.com",
                                 "http://127.0.0.1.nip.io:8852", "ftp://127.0.0.1:8852", "127.0.0.1:8852",
                                 "http://user@127.0.0.1:8852", "http://127.0.0.1:8850"])
def test_the_runner_refuses_a_chart_service_that_is_not_local(url, monkeypatch, capsys):
    monkeypatch.setattr(host, "run", lambda *a, **k: pytest.fail("the runner started"))
    with pytest.raises(SystemExit) as e:
        cli.main(["--charts", url])
    assert e.value.code == 2 and "--charts" in capsys.readouterr().err


@pytest.mark.parametrize("url", ["http://127.0.0.1:8852", "http://localhost:8853/"])
def test_the_runner_starts_on_a_local_chart_service(url, monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(host, "run", lambda charts, at=None: ran.append((charts, at)))
    assert cli.main(["--charts", url, "--root", str(tmp_path)]) == 0
    assert ran == [(url.rstrip("/"), str(tmp_path))]


def test_the_launchd_job_runs_the_runner_and_is_kept_alive():
    import plistlib
    tpl = REPO / "deploy" / "com.ramosquant.homebase-labrun.plist.template"
    job = plistlib.loads(tpl.read_bytes().replace(b"__REPO__", b"/repo"))
    assert job["Label"] == "com.ramosquant.homebase-labrun"
    assert job["ProgramArguments"] == ["/repo/.venv/bin/python", "-m", "homebase.labrun"]
    assert job["WorkingDirectory"] == "/repo" and job["KeepAlive"] is True and job["Nice"] >= 5
    assert "homebase-labrun" not in (REPO / "deploy" / "install.sh").read_text()     # not installed by this task


def test_the_daily_bars_are_the_completed_days_before_the_date(tmp_path):
    from homebase.backtest.tape import TapeStore
    from tests.charts_util import rows as csv_rows, write_archive
    base = tmp_path / "ticks"
    for d, px in ((dt.date(2024, 3, 1), 100.0), (MON, 110.0), (D, 120.0)):
        write_archive(base, "NQ", d, "NQH4", csv_rows(ms_of("09:30", d=d), [px, px + 5, px - 5, px + 1] * 300))
    got = host.daily_bars("NQ", D, TapeStore(base, tmp_path / "cache"))
    assert got == [{"date": "2024-03-01", "h": 105.0, "l": 95.0, "c": 101.0},
                   {"date": "2024-03-04", "h": 115.0, "l": 105.0, "c": 111.0}]
