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
from homebase.labrun.host import Runner, StrategyDay, TickClient, run_day
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
    day.on_clock(ms_of("16:00"))
    s = day.summary()
    assert day.state == s["state"] == "done" and day.child_alive() is False
    assert s["trades"] == [{"side": "long", "qty": 1, "entry_t": "09:30:02", "entry_px": 21001.25, "exit_t": "09:30:02",
                            "exit_px": 21000.75, "reason": "eod", "net": -14.0}]
    assert s["net"] == -14.0


def test_a_day_made_after_its_window_is_run_from_the_prints_and_ends_done(days):
    day = days(MARKET_930)
    day.on_ticks(ticks("09:29:50", [21000.0] * 20) + ticks("15:54:59", [21010.0] * 3) + ticks("16:00:01", [21020.0]))
    assert day.state == "running" and len(day.summary()["trades"]) == 1
    day.on_clock(ms_of("17:00"))
    assert day.state == "done" and day.summary()["trades"][0]["reason"] == "time"


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
    "raises": ('        raise RuntimeError("boom")', "Strategy error: RuntimeError: boom"),
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
    (HEAD + "class Bad(Strategy:\n    pass\n", "Strategy error: SyntaxError"),
    (HEAD + "x = 1\n", "Strategy error: a draft defines exactly one Strategy subclass (found 0)"),
    (HEAD + 'class W(Strategy):\n    id, name, root = "w", "W", "NQ"\n    session_window = ("nine", "ten")\n',
     "Strategy error: "),
])
def test_a_strategy_that_does_not_start_is_stopped(source, why, days):
    day = days(source)
    assert day.state == "stopped" and day.summary()["why"].startswith(why) and day.child_alive() is False
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
    assert (bad.state, bad.summary()["why"]) == ("stopped", "The daily bars could not be read: disk")
    assert bad.child_alive() is False


def test_an_event_that_breaks_in_the_runner_itself_stops_the_day(days, monkeypatch):
    """Not the strategy's fault, but a day that lost an event half way cannot be trusted: stop it and say so."""
    day = days(MARKET_930)
    monkeypatch.setattr(host.ShadowFills, "apply", lambda self, intents: 1 / 0)
    day.on_ticks(ticks("09:29:50", [21000.0] * 20))
    assert day.state == "stopped" and day.child_alive() is False
    assert day.summary()["why"] == "The runner could not go on: ZeroDivisionError: division by zero"


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
    day = days(MARKET_930)
    day.on_ticks(ticks("09:29:50", [21000.0] * 5))                           # the newest print is 09:29:54
    day.on_clock(ms_of("09:29:55"))
    assert day.summary()["why"] is None
    day.on_clock(ms_of("09:29:57"))                                          # 3 s behind: late starts to count
    day.on_clock(ms_of("09:30:01"))
    assert day.summary()["why"] is None                                      # 4 s running
    day.on_clock(ms_of("09:30:02", 1))                                       # 5 s running, and 09:30:00 fires by the clock
    s = day.summary()
    assert (s["state"], s["why"]) == ("running", "Prices are late.")
    assert s["orders"] == [{"t": "09:30:00", "text": "Buy at market, stop 20,990.00", "refused": "Prices are late."}]
    day.on_ticks(ticks("09:30:02", [21001.0]))                               # a fresh print
    assert day.summary()["why"] is None
    assert not day.fills.flat                                                # shadow: the refused order still filled


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
MON = dt.date(2024, 3, 4)


class Desk:
    """A Runner on a temp store, fed by hand: what the tick client and the main loop would hand it."""

    def __init__(self, tmp_path):
        self.at = tmp_path / "desklab"
        self.wall = [1000.0]                         # the runner's wall clock, moved by hand
        self.last_clock = None
        self.r = Runner(at=self.at, source="http://127.0.0.1:8852", spawn=plain, deadline_s=0.3, daily=lambda root, d: [],
                        wall=lambda: self.wall[0])

    def promote(self, source=MARKET_930, name="lab_x", **kw):
        return store.put(rec(source, name, **kw), self.at)

    def clock(self, hms, d=D, ms=0):
        self.last_clock = ms_of(hms, ms, d)
        self.r.on_clock(self.last_clock)

    def rows(self, start, prices, d=D, root="NQ", step_ms=1000):
        t0 = ms_of(start, d=d)
        self.r.on_rows(root, [[t0 + i * step_ms, p, 1] for i, p in enumerate(prices)])

    def today(self, name="lab_x", d=D):
        """The day file, once the second a summary may wait to be written is over (the stream's next clock)."""
        self.wall[0] += 1.5
        if self.last_clock is not None:
            self.r.on_clock(self.last_clock)
        return store.get_day(name, d.isoformat(), self.at)

    def journal(self, name="lab_x"):
        f = self.at / name / "journal.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.is_file() else []


@pytest.fixture
def desk(tmp_path):
    made = []

    def make():
        made.append(Desk(tmp_path))
        return made[-1]
    yield make
    for d in made:
        d.r.close()


def test_a_promoted_strategy_is_hosted_fed_and_written_down(desk):
    k = desk()
    k.promote()
    k.clock("09:29:00")
    k.r.sync()
    assert k.r.hosting() == [] and k.r.roots() == ["NQ"] and k.today() is None    # no print for its market yet
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
    k.clock("16:00:00")
    assert k.today()["state"] == "done" and k.r.hosting() == []
    assert [x["kind"] for x in k.journal()] == ["order", "order", "trade"]
    assert k.journal()[-1]["reason"] == "time" and k.journal()[-1]["net"] == k.today()["net"]
    k.r.sync()
    assert k.today()["state"] == "done"                                      # a finished day is not started again


def test_a_strategy_that_appears_late_is_caught_up_from_todays_prints_with_no_journal(desk):
    k = desk()
    k.clock("09:00:00")
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
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    k.rows("09:30:00", [21000.0] * 80)
    k.clock("09:32:00")
    k.r.sync()
    assert (k.today()["state"], k.today()["why"]) == ("stopped", why)
    assert [x["kind"] for x in k.journal()] == ["order", "stop", "trade"] and k.journal()[1]["why"] == why


def test_switched_off_or_removed_its_child_is_stopped_and_the_day_reads_off(desk):
    k = desk()
    k.promote()
    k.promote(name="lab_y")
    k.clock("09:00:00")
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


def test_changed_code_gets_a_fresh_day(desk):
    k = desk()
    k.promote()
    k.clock("09:00:00")
    k.rows("09:29:50", [21000.0] * 9)
    k.rows("09:30:00", [21000.0, 21001.0])
    k.r.sync()
    old = k.r.day("lab_x")
    assert len(k.today()["orders"]) == 1
    newer = MARKET_930.replace("- 10", "- 20")
    k.promote(newer)
    k.r.sync()
    assert not old.child_alive() and k.r.day("lab_x") is not old
    s = k.today()
    assert s["sha256"] == rec(newer)["sha256"] and [o["text"] for o in s["orders"]] == ["Buy at market, stop 20,980.00"]


def test_at_the_date_change_every_day_is_finished_and_new_days_start(desk):
    k = desk()
    k.promote()
    k.clock("09:00:00", MON)
    k.rows("09:29:50", [21000.0] * 9, MON)
    k.rows("09:30:00", [21000.0, 21001.0], MON)
    k.r.sync()
    old = k.r.day("lab_x")
    k.rows("23:59:58", [21050.0, 21051.0], MON)
    k.rows("00:00:00", [21052.0], D, step_ms=1)                              # a print of the new day, before its clock
    k.clock("00:00:01", D)
    assert not old.child_alive() and k.today(d=MON)["state"] == "done" and len(k.today(d=MON)["trades"]) == 1
    assert k.r.prints("NQ") == 1                                             # yesterday's prints are dropped
    assert k.r.day("lab_x") is not old and k.today(d=D)["state"] == "waiting"


def test_nothing_is_hosted_on_a_weekend(desk):
    k = desk()
    k.promote()
    sat = dt.date(2024, 3, 9)
    k.clock("09:00:00", sat)
    k.rows("09:29:50", [21000.0] * 9, sat)
    k.r.sync()
    assert k.r.hosting() == [] and k.today(d=sat) is None


def test_the_heartbeat_says_who_is_hosted_and_how_old_the_prices_are(desk):
    k = desk()
    k.promote()
    k.promote(name="es_one", root="ES")
    k.clock("09:00:00")
    k.rows("09:29:50", [21000.0] * 9)
    k.clock("09:29:59")
    k.r.sync()
    k.r.beat()
    b = store.get_runner(k.at)
    assert set(b) == {"pid", "seen_utc", "source", "prices", "hosting"} and b["source"] == "http://127.0.0.1:8852"
    assert b["hosting"] == ["lab_x"] and b["prices"] == {"ES": {"age_s": None, "late": True},
                                                         "NQ": {"age_s": 1.0, "late": False}}
    assert abs((dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(b["seen_utc"])).total_seconds()) < 5
    for s in ("09:30:02", "09:30:05", "09:30:08"):                           # no print for more than 2 s, 5 s running
        k.clock(s)
    k.r.beat()
    assert store.get_runner(k.at)["prices"]["NQ"] == {"age_s": 10.0, "late": True}
    k.rows("09:30:08", [21000.0])
    k.clock("09:30:09")
    k.wall[0] += 6                                                           # no clock from the stream for 6 s
    k.r.beat()
    assert store.get_runner(k.at)["prices"]["NQ"] == {"age_s": None, "late": True}


def test_a_stuck_strategy_does_not_hold_up_another_in_the_runner(desk):
    k = desk()
    k.promote(planted(STOPS["spins"][0]), name="lab_bad")
    k.promote(MARKET_930.replace('"09:30:00", "15:55"', '"09:31:00", "15:55"')
              .replace('et_time == "09:30:00"', 'et_time == "09:31:00"'), name="lab_good")
    k.clock("09:00:00")
    k.rows("09:29:50", [21000.0] * 9)
    k.r.sync()
    t = time.monotonic()
    k.rows("09:30:00", [21000.0] * 80)
    k.clock("09:31:21")
    assert time.monotonic() - t < 2.0
    assert k.today("lab_bad")["why"] == "Too slow: no answer in 0.3 s."
    assert [o["t"] for o in k.today("lab_good")["orders"]] == ["09:31:00"]


# ---------------------------------------------------------------- the tick client
def client(handler, roots=("NQ",), now_ms=ms_of("10:00"), **kw):
    got, slept = [], []
    c = TickClient("http://127.0.0.1:8852", lambda: list(roots), got.append, transport=httpx.MockTransport(handler),
                   sleep=slept.append, wall_ms=lambda: now_ms, **kw)
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


def test_the_client_asks_from_midnight_then_from_its_oldest_newest_print_and_backs_off():
    asked = []
    bodies = [sse(("clock", {"now_ms": ms_of("10:00")}), (None, {"root": "NQ", "rows": [[100, 1.0, 1], [200, 2.0, 2]]}),
                  (None, {"root": "ES", "rows": [[150, 5.0, 1]]}), ("live", {})),
              None, None,
              sse((None, {"root": "NQ", "rows": [[200, 2.0, 2], [200, 2.5, 1], [300, 3.0, 1]]}),
                  (None, {"root": "ES", "rows": [[150, 5.0, 1], [160, 6.0, 1]]}), ("clock", {"now_ms": ms_of("10:00", 5)})),
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
    midnight = ms_of("00:00")
    assert asked == ([{"roots": "NQ,ES", "since_ms": str(midnight)}] + [{"roots": "NQ,ES", "since_ms": "150"}] * 3
                     + [{"roots": "NQ,ES", "since_ms": "160"}])
    assert [x for x in got if x[0] == "ticks"] == [
        ("ticks", "NQ", [[100, 1.0, 1], [200, 2.0, 2]]), ("ticks", "ES", [[150, 5.0, 1]]),
        ("ticks", "NQ", [[200, 2.5, 1], [300, 3.0, 1]]), ("ticks", "ES", [[160, 6.0, 1]])]
    assert [x for x in got if x[0] == "clock"] == [("clock", ms_of("10:00")), ("clock", ms_of("10:00", 5))]
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
    assert slept == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0] and not [x for x in got if x[0] == "ticks"]


def test_a_stream_whose_clock_is_on_an_earlier_day_is_asked_again_from_that_days_midnight():
    """A replayed session: the service's clock is the replay's, not the wall's."""
    asked = []
    stop = host.threading.Event()
    replayed = ms_of("09:40", d=MON)

    def handler(req):
        asked.append(int(req.url.params["since_ms"]))
        if len(asked) == 3:
            stop.set()
        return httpx.Response(200, content=sse(("clock", {"now_ms": replayed}),
                                               (None, {"root": "NQ", "rows": [[replayed - 5, 1.0, 1]]})))

    c, got, slept = client(handler)
    assert c.fresh("NQ", [[ms_of("09:59"), 9.0, 1]])                         # held from the live day it was reading before
    c.run(stop)
    assert asked == [ms_of("09:59"), ms_of("00:00", d=MON), replayed - 5] and slept == [1.0]   # the second: at once
    assert [x for x in got if x[0] == "ticks"] == [("ticks", "NQ", [[replayed - 5, 1.0, 1]])]
    assert [x for x in got if x[0] == "clock"] == [("clock", replayed)]


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
    assert got == [("ticks", "NQ", [[5, 1.0, 1]])] and slept == [1.0, 2.0, 4.0, 1.0]


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
                   transport=httpx.MockTransport(handler), sleep=slept.append, wall_ms=lambda: ms_of("10:00"))
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
