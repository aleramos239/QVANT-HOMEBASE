"""Self-fire timer: gate → stage → anchor → fire, and every fail-safe."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.marketdata import TRADE_HISTORY, TradovateMD
from homebase.timer import FIRE_LATE_MAX_S, SelfTimer
from tests.test_engine import Clock, FakeAdapter

FIX = json.loads((Path(__file__).parent / "fixture_gate_nq2024.json").read_text())
ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeMD:
    def __init__(self, bars=None, last_trade=None, clock=None):
        self.connected = True
        self.bars = bars if bars is not None else FIX["bars"]
        self.last_trade = last_trade          # default price for any feed
        self.prices: dict = {}                # per-feed prices, if set
        self.subs = []
        self.clock = clock                    # the timer's clock: a trade is received "now"

    async def connect(self): ...
    async def daily_bars(self, symbol, n=60): return self.bars[-n:]
    async def subscribe_quote(self, symbol):
        self.subs.append(symbol); return symbol
    async def unsubscribe_quote(self, sym): self.subs.remove(sym)

    def last(self, sym, before=None):
        # these fixed prices stand for trades printed before the open: every cutoff passes them
        px = self.prices.get(sym, self.last_trade)
        seen = self.clock().timestamp() if self.clock else time.time()
        return (px, seen) if px is not None else (None, 0.0)

    def trade_push(self, sym, before=None):
        return None                           # no tape: the journal's stamp fields stay null


def iso_z(when):
    """An aware datetime as Tradovate's quote `timestamp`: ISO, ms, UTC 'Z'."""
    return when.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TapeMD(FakeMD):
    """Trades arrive as Tradovate quote pushes, and are kept and read back by the REAL
    TradovateMD code (_on_event / last / trade_push). Each push is RECEIVED at a local
    time the test sets, whatever `timestamp` the exchange put on it."""
    _on_event = TradovateMD._on_event
    last = TradovateMD.last
    trade_push = TradovateMD.trade_push
    SAME = object()

    def __init__(self, **kw):
        super().__init__(**kw)
        self._trades, self._tape, self._cid_sym = {}, {}, {}
        self._received = 0.0
        self._clock = lambda: self._received

    async def subscribe_quote(self, symbol):
        self._cid_sym[1000 + len(self._cid_sym)] = symbol      # the reply's subscriptionId
        return await super().subscribe_quote(symbol)

    def push(self, symbol, seen, px, stamp=SAME):
        """One trade push for a subscribed `symbol`, RECEIVED at local `seen`. The exchange
        stamped it `stamp`: by default the same instant (ISO ms 'Z'); None = no timestamp."""
        cid = next(c for c, s in self._cid_sym.items() if s == symbol)
        q = {"contractId": cid, "entries": {"Trade": {"price": px, "size": 1}}}
        stamp = iso_z(seen) if stamp is TapeMD.SAME else stamp
        if stamp is not None:
            q["timestamp"] = stamp
        self._received = seen.timestamp()
        self._on_event({"e": "md", "d": {"quotes": [q]}})


def et(h, m, s=0, us=0, date=(2026, 9, 14)):
    """An ET wall time (a Monday by default), DST-aware."""
    return dt.datetime(*date, h, m, s, us, tzinfo=ET)


def at(clock, h, m, s=0, us=0, date=(2026, 9, 14)):
    clock.dt = et(h, m, s, us, date=date).astimezone(UTC)


def mk(tmp_path, *, last_trade=24500.0, clock=None, armed=False, md=None):
    clock = clock or Clock()
    cfg = AppCfg(armed=armed, webhook_secret="s",
                 accounts={"main": AccountCfg(keyring_key="k",
                                              account_name="MAIN")},
                 book={"nq930": [{"account": "main", "qty": 3}]},
                 strategies={"nq930": StrategyCfg(
                     symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0,
                     tp_pts=15.0, enabled=True, gated=True, self_fire=True)})
    engine = Engine(cfg, {"main": FakeAdapter("main")}, now_fn=clock,
                    root=tmp_path)
    if md is None:
        md = FakeMD(last_trade=last_trade, clock=clock)
    timer = SelfTimer(cfg, engine, md_factory=lambda: md, now_fn=clock)
    return timer, engine, md, clock


def events(tmp_path):
    p = tmp_path / "journal.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def _drive_to_fire(timer, clock):
    clock.set_et(9, 21); run(timer.tick())        # gate
    clock.set_et(9, 29); run(timer.tick())        # stage
    clock.set_et(9, 30); run(timer.tick())        # fire


def test_timer_gates_stages_and_fires_dry_run(tmp_path):
    timer, engine, md, clock = mk(tmp_path)
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert st["gate"] is True and st["adx"] == 22.42     # fixture NQ 2024 tail
    assert st["stage"] == "fired" and st["anchor"] == 24500.0
    assert md.subs == ["NQ"]                              # quote staged
    ev = {e["event"]: e for e in events(tmp_path)}
    assert ev["timer_gate"]["gate"] is True
    assert ev["dry_run"]["source"] == "timer"
    assert ev["dry_run"]["upper"] == 24510.0 and ev["dry_run"]["lower"] == 24490.0
    assert ev["timer_fired"]["result"] is True


def test_timer_skips_chop_day(tmp_path, monkeypatch):
    timer, engine, md, clock = mk(tmp_path)
    monkeypatch.setattr("homebase.timer.trend_gate", lambda bars: (False, 12.0))
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "skipped"
    assert not any(e["event"] == "dry_run" for e in events(tmp_path))


def test_timer_refuses_unknown_gate(tmp_path, monkeypatch):
    timer, engine, md, clock = mk(tmp_path)
    monkeypatch.setattr("homebase.timer.trend_gate", lambda bars: (None, None))
    _drive_to_fire(timer, clock)
    assert timer.status()["strategies"]["nq930"]["stage"] == "error"
    assert not any(e["event"] == "dry_run" for e in events(tmp_path))


def test_timer_refuses_stale_anchor(tmp_path):
    timer, engine, md, clock = mk(tmp_path, last_trade=None)
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "error" and "anchor" in st["error"]
    assert not any(e["event"] == "dry_run" for e in events(tmp_path))


def test_timer_defers_when_day_already_acted(tmp_path):
    timer, engine, md, clock = mk(tmp_path)
    engine._state("nq930", "main").status = "placed"      # e.g. TV won the race
    _drive_to_fire(timer, clock)
    assert timer.status()["strategies"]["nq930"]["stage"] == "done"
    assert any(e["event"] == "timer_deferred" for e in events(tmp_path))


def test_timer_never_fires_outside_the_window(tmp_path):
    """A restart at any hour must not stage/fire on a stale anchor."""
    import datetime as _dt
    cases = [(11, 0), (14, 30), (19, 15)]
    for hh, mm in cases:
        clock = Clock()
        timer, engine, md, _ = mk(tmp_path, clock=clock)
        clock.set_et(hh, mm)
        run(timer.tick())
        st = timer.status()["strategies"]["nq930"]
        assert st["stage"] == "missed", f"{hh}:{mm} -> {st['stage']}"
        assert st["anchor"] is None
        assert md.subs == []                       # never even subscribed
        assert not any(e["event"] in ("timer_fired", "dry_run")
                       for e in events(tmp_path))

    # and the exact case seen in production: 23:03 ET (= 03:03 UTC next day)
    clock = Clock()
    timer, engine, md, _ = mk(tmp_path, clock=clock)
    clock.dt = _dt.datetime(2026, 9, 15, 3, 3,
                            tzinfo=_dt.timezone.utc)          # Mon 23:03 ET
    run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "missed"
    assert md.subs == []


def test_timer_quiet_on_weekend(tmp_path):
    timer, engine, md, clock = mk(tmp_path)
    clock.dt = clock.dt.replace(day=13)                   # Sunday 2026-09-13
    clock.set_et(9, 30); clock.dt = clock.dt.replace(day=13)
    run(timer.tick())
    assert timer.status()["strategies"] == {}


def test_timer_sleeps_exactly_to_the_930_fire(tmp_path):
    """Staged and 9:30:00 under a tick away: sleep exactly the time left,
    so the fire lands on 9:30:00.000 — not up to 200 ms after it."""
    timer, engine, md, clock = mk(tmp_path)
    assert timer._sleep_s() == 0.2                   # nothing staged yet
    clock.set_et(9, 21); run(timer.tick())
    clock.set_et(9, 29); run(timer.tick())           # staged
    clock.dt = clock.dt.replace(second=59, microsecond=950000)
    assert abs(timer._sleep_s() - 0.05) < 1e-6       # 9:29:59.950 -> 50 ms
    clock.dt = clock.dt.replace(second=0, microsecond=0)
    assert timer._sleep_s() == 0.2                   # 9:29:00 -> normal tick


def _add_ym(engine):
    engine.cfg.strategies["ym930"] = StrategyCfg(
        symbol="YM", qty=9, offset_pts=20.0, sl_pts=5.0, tp_pts=15.0,
        enabled=True, gated=False, self_fire=True)
    engine.cfg.book["ym930"] = [{"account": "main", "qty": 9}]


def test_each_strategy_is_anchored_on_its_own_symbol(tmp_path):
    """NQ and YM both on the app timer: each gets its own quote feed and is
    anchored on its OWN last trade — YM must never be priced off NQ."""
    timer, engine, md, clock = mk(tmp_path)
    _add_ym(engine)
    md.prices = {"NQ": 24500.0, "YM": 46000.0}
    _drive_to_fire(timer, clock)
    assert sorted(md.subs) == ["NQ", "YM"]
    dry = {e["strategy"]: e for e in events(tmp_path) if e["event"] == "dry_run"}
    assert (dry["nq930"]["upper"], dry["nq930"]["lower"]) == (24510.0, 24490.0)
    assert (dry["ym930"]["upper"], dry["ym930"]["lower"]) == (46020.0, 45980.0)


def test_due_strategies_fire_together(tmp_path):
    """At 9:30 no strategy waits on another's broker round trip."""
    timer, engine, md, clock = mk(tmp_path)
    _add_ym(engine)
    md.prices = {"NQ": 24500.0, "YM": 46000.0}
    orig, seen = engine.handle_alert, {"now": 0, "max": 0}

    async def slow(payload, **kw):
        seen["now"] += 1
        seen["max"] = max(seen["max"], seen["now"])
        await asyncio.sleep(0.01)                  # a broker round trip
        seen["now"] -= 1
        return await orig(payload, **kw)

    engine.handle_alert = slow
    _drive_to_fire(timer, clock)
    assert seen["max"] == 2
    st = timer.status()["strategies"]
    assert st["nq930"]["stage"] == st["ym930"]["stage"] == "fired"


# --- the fire's grace: orders go out within FIRE_LATE_MAX_S of 09:30:00.000, on the
# --- last trade RECEIVED before 09:30:00.000 (the research anchor), or not at all
def test_staged_at_092959_9_fires_at_093000_on_the_last_trade_received_before_the_open(tmp_path):
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())                          # gate
    at(clock, 9, 29, 59, 900000); run(timer.tick())              # stage: the quote is subscribed
    assert timer.status()["strategies"]["nq930"]["stage"] == "staged"
    md.push("NQ", et(9, 29, 59, 950000), 24500.0)
    md.push("NQ", et(9, 29, 59, 999000), 24500.25,               # the last print received before the open --
            stamp=iso_z(et(9, 30, 0, 4000)))                      # its stamp says after: never read
    md.push("NQ", et(9, 30, 0), 24503.0,                          # received AT the open: not before it,
            stamp=iso_z(et(9, 29, 59, 990000)))                   # however early it was stamped
    md.push("NQ", et(9, 30, 0, 20000), 24507.5)
    step = timer._sleep_s()
    assert abs(step - 0.1) < 1e-6                                # exactly the time left
    clock.dt += dt.timedelta(seconds=step); run(timer.tick())    # 09:30:00.000
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["anchor"] == 24500.25
    ev = events(tmp_path)
    assert [(e["upper"], e["lower"]) for e in ev if e["event"] == "dry_run"] == [(24510.25, 24490.25)]
    assert not any(e["event"] == "timer_missed" for e in ev)


def test_a_tick_at_093000_4_still_fires_and_still_on_the_pre_open_trade(tmp_path):
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 29, 59, 980000), 24500.0)
    md.push("NQ", et(9, 30, 0, 100000), 24512.0)                 # after the open: never the anchor
    md.push("NQ", et(9, 30, 0, 350000), 24519.0)
    at(clock, 9, 30, 0, 400000); run(timer.tick())               # 0.4 s late: inside the grace
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["anchor"] == 24500.0
    assert [(e["upper"], e["lower"]) for e in events(tmp_path) if e["event"] == "dry_run"] == \
        [(24510.0, 24490.0)]


@pytest.mark.parametrize("stamp", [None, "2026-09-14T09:29:59.990", 1789392599990, "not a time",
                                   {"t": 1}, "2026-09-14T13:29:59.990z"],
                         ids=["missing", "no-zone", "epoch-ms", "garbage", "an-object", "lowercase-z"])
def test_the_fire_never_needs_the_pushes_own_timestamp(tmp_path, stamp):
    """Review 2026-09-28: the quote push's `timestamp` has never been seen live. Missing,
    zone-less, epoch-ms or anything else, the fire anchors exactly as before: on the last
    trade received before 09:30:00.000."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 29, 59, 990000), 24500.0, stamp=stamp)
    md.push("NQ", et(9, 30, 0, 200000), 24511.0, stamp=stamp)    # after the open
    at(clock, 9, 30, 0, 300000); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["anchor"] == 24500.0
    fired = [e for e in events(tmp_path) if e["event"] == "timer_fired"]
    assert len(fired) == 1 and fired[0]["anchor_seen"] == "09:29:59.990"
    assert fired[0]["anchor_stamp_raw"] == (None if stamp is None else str(stamp)[:40])


def test_the_fire_journals_the_anchor_push_and_the_newest_push(tmp_path):
    """For the first live mornings: when each push was received, the `timestamp` it carried
    (raw, parsed to ET) and received minus stamped -- the field's format and the clock/feed
    skew, measured."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 29, 59, 990000), 24500.0,                # 30 ms in flight
            stamp=iso_z(et(9, 29, 59, 960000)))
    md.push("NQ", et(9, 30, 0, 300000), 24511.0,                 # an epoch-ms number, 42 ms in flight
            stamp=round(et(9, 30, 0, 258000).timestamp() * 1000))
    at(clock, 9, 30, 0, 400000); run(timer.tick())
    fired = next(e for e in events(tmp_path) if e["event"] == "timer_fired")
    assert {k: fired[k] for k in fired if k.startswith(("anchor_", "newest_"))} == {
        "anchor_seen": "09:29:59.990", "anchor_stamp_raw": "2026-09-14T13:29:59.960Z",
        "anchor_stamp": "09:29:59.960", "anchor_lag_ms": 30,
        "newest_seen": "09:30:00.300", "newest_stamp_raw": "1789392600258",
        "newest_stamp": "09:30:00.258", "newest_lag_ms": 42}
    assert fired["anchor"] == 24500.0


def test_an_anchor_refusal_journals_the_pushes_it_saw(tmp_path):
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 30, 0, 100000), 24511.0, stamp=None)     # the first print arrives after the open
    at(clock, 9, 30, 0, 200000); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "error" and "anchor" in st["error"]
    err = next(e for e in events(tmp_path) if e["event"] == "timer_error")
    assert {k: err[k] for k in err if k.startswith(("anchor_", "newest_"))} == {
        "anchor_seen": None, "anchor_stamp_raw": None, "anchor_stamp": None, "anchor_lag_ms": None,
        "newest_seen": "09:30:00.100", "newest_stamp_raw": None, "newest_stamp": None,
        "newest_lag_ms": None}
    assert not any(e["event"] in ("timer_fired", "dry_run") for e in events(tmp_path))


@pytest.mark.parametrize("hms", [(9, 30, 2), (9, 37, 0), (9, 44, 59)])
def test_a_restart_after_the_grace_on_an_idle_day_is_missed_and_places_nothing(tmp_path, hms):
    """The desk (re)starts -- or the strategy is switched on / booked -- after the open on a
    day it has not traded: it gates and stages as ever, but never fires on a post-open price."""
    timer, engine, md, clock = mk(tmp_path, armed=True)          # ARMED: a fire would place
    at(clock, *hms); run(timer.tick())                           # a fresh SelfTimer = a restart
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "missed" and st["anchor"] is None
    miss = [e for e in events(tmp_path) if e["event"] == "timer_missed"]
    assert [(e["reason"], e["at"], e["grace_s"]) for e in miss] == \
        [("late_start", "%02d:%02d:%02d.000" % hms, FIRE_LATE_MAX_S)]
    assert miss[0]["late_s"] == (hms[1] - 30) * 60 + hms[2]
    at(clock, *hms, 500000); run(timer.tick())                   # the next tick: still missed, said once
    assert timer.status()["strategies"]["nq930"]["stage"] == "missed"
    ev = events(tmp_path)
    assert sum(e["event"] == "timer_missed" for e in ev) == 1
    assert not any(e["event"] in ("timer_fired", "dry_run", "placed") for e in ev)
    assert engine.adapters["main"].brackets == [] and engine.adapters["main"].orders == []


def test_a_staged_strategy_whose_tick_wakes_past_the_grace_is_missed(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True)
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged in time
    at(clock, 9, 30, 3); run(timer.tick())                       # ... but the loop stalled 3 s
    assert timer.status()["strategies"]["nq930"]["stage"] == "missed"
    ev = events(tmp_path)
    assert [(e["reason"], e["late_s"]) for e in ev if e["event"] == "timer_missed"] == \
        [("late_fire", 3.0)]
    assert not any(e["event"] in ("timer_fired", "placed") for e in ev)
    assert engine.adapters["main"].brackets == []


def test_a_fire_held_past_the_grace_inside_its_own_tick_is_missed(tmp_path):
    """nq930 checks in on time at 09:30:00.000, but ym930 -- switched on just before the
    open -- stages in the same tick and its quote subscription takes 1.5 s: nq930's orders
    would leave at 09:30:01.5 on levels from 09:30:00. Neither fires; nothing is placed."""
    timer, engine, md, clock = mk(tmp_path, armed=True)
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # nq930 staged
    _add_ym(engine)                                              # ym930 switched on
    sub = md.subscribe_quote

    async def slow(symbol):
        if symbol == "YM":
            clock.dt += dt.timedelta(seconds=1.5)                # its round trip holds the tick
        return await sub(symbol)

    md.subscribe_quote = slow
    at(clock, 9, 30); run(timer.tick())
    st = timer.status()["strategies"]
    assert st["nq930"]["stage"] == st["ym930"]["stage"] == "missed"
    ev = events(tmp_path)
    assert {e["strategy"]: (e["reason"], e["late_s"]) for e in ev if e["event"] == "timer_missed"} == \
        {"nq930": ("late_fire", 1.5), "ym930": ("late_start", 1.5)}
    assert not any(e["event"] in ("timer_fired", "dry_run", "placed") for e in ev)
    assert engine.adapters["main"].brackets == []


@pytest.mark.parametrize("status", ["placed", "live", "done"])
def test_a_restart_after_the_open_on_a_day_that_already_fired_is_still_done(tmp_path, status):
    timer, engine, md, clock = mk(tmp_path, armed=True)
    engine._state("nq930", "main").status = status              # it fired before the restart
    at(clock, 9, 37); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "done"
    ev = events(tmp_path)
    assert [e["status"] for e in ev if e["event"] == "timer_deferred"] == [status]
    assert not any(e["event"] in ("timer_missed", "timer_fired", "dry_run", "placed") for e in ev)
    assert engine.adapters["main"].brackets == []


def test_weekends_stay_quiet_and_a_closed_weekday_is_any_weekday(tmp_path):
    """Weekends: nothing at all, on time or late. The timer keeps no holiday calendar, so a
    closed weekday (Christmas, a Friday) runs the weekday rules: on time with no trade it
    refuses as it always has, and a late start is missed like on any other day."""
    for i, hms in enumerate(((9, 30, 0, 400000), (9, 37, 0))):
        root = tmp_path / f"sat{i}"
        root.mkdir()
        timer, engine, md, clock = mk(root, armed=True)
        at(clock, *hms, date=(2026, 9, 19))                      # Saturday
        run(timer.tick())
        assert timer.status()["strategies"] == {}
        assert events(root) == []

    xmas = (2026, 12, 25)
    root = tmp_path / "xmas"
    root.mkdir()
    timer, engine, md, clock = mk(root, last_trade=None)         # CME closed: no trade
    at(clock, 9, 21, date=xmas); run(timer.tick())
    at(clock, 9, 29, date=xmas); run(timer.tick())
    at(clock, 9, 30, date=xmas); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "error" and "anchor" in st["error"]
    assert not any(e["event"] in ("timer_missed", "dry_run") for e in events(root))

    root = tmp_path / "xmas-late"
    root.mkdir()
    timer, engine, md, clock = mk(root)
    at(clock, 9, 37, date=xmas); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "missed"
    assert [e["reason"] for e in events(root) if e["event"] == "timer_missed"] == ["late_start"]


@pytest.mark.parametrize("date", [(2026, 3, 9), (2026, 11, 2), (2026, 1, 5)])
def test_the_fire_the_grace_and_the_anchor_follow_new_york_time_across_dst(tmp_path, date):
    """The Mondays after the spring-forward and fall-back Sundays, and a winter day: 09:30 ET
    is 13:30 UTC under EDT and 14:30 UTC under EST -- the fire, its grace and the anchor's
    cutoff all move with it."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21, date=date); run(timer.tick())
    at(clock, 9, 29, date=date); run(timer.tick())               # staged
    md.push("NQ", et(9, 29, 59, 900000, date=date), 24500.0)
    md.push("NQ", et(9, 30, 0, 100000, date=date), 24512.0)
    at(clock, 9, 29, 59, 950000, date=date)
    assert abs(timer._sleep_s() - 0.05) < 1e-6
    at(clock, 9, 30, 0, 400000, date=date); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["anchor"] == 24500.0

    root = tmp_path / "late"
    root.mkdir()
    timer, engine, md, clock = mk(root, armed=True)
    at(clock, 9, 30, 2, date=date); run(timer.tick())
    assert [(e["reason"], e["at"], e["late_s"]) for e in events(root)
            if e["event"] == "timer_missed"] == [("late_start", "09:30:02.000", 2.0)]
    assert engine.adapters["main"].brackets == []


def test_the_md_anchor_is_the_last_trade_received_before_the_open(tmp_path, monkeypatch):
    """TradovateMD.last(before=): the latest trade from a push RECEIVED strictly before the
    cutoff (the research's "last print before 09:30:00.000"), whenever it is asked -- by the
    local receive clock; the push's own `timestamp` is kept, raw, for the journal only."""
    import homebase.marketdata as md_mod
    monkeypatch.setattr(md_mod, "state_dir", lambda: tmp_path)
    m = TradovateMD("k", "demo", token_provider=lambda: "tok")
    m._cid_sym.update({3267315: "NQZ6", 4706811: "YMZ6"})
    now = {"t": 0.0}
    m._clock = lambda: now["t"]

    def push(seen, px, stamp=None, cid=3267315):
        q = {"contractId": cid, "entries": {"Trade": {"price": px, "size": 1}}}
        if stamp is not None:
            q["timestamp"] = stamp
        now["t"] = seen.timestamp()
        m._on_event({"e": "md", "d": {"quotes": [q]}})

    cut = et(9, 30).timestamp()
    assert m.last("NQZ6", before=cut) == (None, 0.0)             # nothing yet
    assert m.trade_push("NQZ6") is None
    push(et(9, 29, 59, 950000), 24500.0, "2026-09-14T13:29:59.920Z")
    push(et(9, 29, 59, 999000), 24500.25, None)                  # the last print received before the open
    push(et(9, 29, 59, 999500), 46000.0, cid=4706811)            # another contract's: never NQ's
    push(et(9, 30, 0), 24503.0, "2026-09-14T13:29:59.990Z")      # received AT the open: not before it
    push(et(9, 30, 0, 180000), 24509.5, 1789392600150)           # epoch ms
    assert m.last("NQZ6", before=cut) == (24500.25, et(9, 29, 59, 999000).timestamp())
    assert m.last("NQZ6") == (24509.5, et(9, 30, 0, 180000).timestamp())   # no cutoff: the latest
    assert m.last("YMZ6", before=cut)[0] == 46000.0
    assert m.trade_push("NQZ6", cut) == (et(9, 29, 59, 999000).timestamp(), 24500.25, None, None)
    seen, px, raw, stamp = m.trade_push("NQZ6")
    assert (px, raw, stamp) == (24509.5, 1789392600150, 1789392600.15)
    for i in range(TRADE_HISTORY):                               # a flood after the open ...
        push(et(9, 30, 0, 500000), 24520.0 + i * 0.25)
    assert m.last("NQZ6", before=cut) == (None, 0.0)             # ... refuses, never a later print


def test_a_pushes_timestamp_parses_only_as_iso_with_a_zone_or_epoch_ms():
    from homebase.marketdata import _stamp
    t = et(9, 29, 59, 950000).timestamp()
    for v in ("2026-09-14T13:29:59.950Z", "2026-09-14T13:29:59.950z", " 2026-09-14T13:29:59.950Z ",
              "2026-09-14T13:29:59.95+00:00", "2026-09-14T09:29:59.950-04:00",
              round(t * 1000), float(round(t * 1000))):
        assert _stamp(v) == pytest.approx(t, abs=1e-6), v
    for v in (None, "", "2026-09-14T13:29:59.950", "not a time", True, float("nan"),
              float("inf"), {"t": 1}, [1]):
        assert _stamp(v) is None, v
