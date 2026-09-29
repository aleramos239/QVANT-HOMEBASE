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

    def pushes(self, sym):
        return 0 if self.prices.get(sym, self.last_trade) is None else 1


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
    pushes = TradovateMD.pushes
    SAME = object()

    def __init__(self, snapshot=None, **kw):
        super().__init__(**kw)
        self._trades, self._tape, self._cid_sym, self._pushes = {}, {}, {}, {}
        self._received = 0.0
        self._clock = lambda: self._received
        self.snapshot = dict(snapshot or {})  # symbol -> the trade its subscription's first quote carries

    async def subscribe_quote(self, symbol):
        self._cid_sym[1000 + len(self._cid_sym)] = symbol      # the reply's subscriptionId
        out = await super().subscribe_quote(symbol)
        if symbol in self.snapshot:                             # received as the subscription answers
            self.push(symbol, self.clock(), self.snapshot[symbol])
        return out

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


def stamps(e):
    """A journal line's fields for the anchor push and the newest push (timer._push_fields)."""
    return {f"{p}_{k}": e[f"{p}_{k}"] for p in ("anchor", "newest")
            for k in ("seen", "stamp_raw", "stamp", "lag_ms")}


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
    elif md.clock is None:
        md.clock = clock
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


def test_timer_waits_with_no_trade_to_anchor_on(tmp_path):
    timer, engine, md, clock = mk(tmp_path, last_trade=None)
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["wait_reason"], st["wait_text"]) == \
        ("waiting", "no_pushes", "no quote pushes at all for NQ")
    assert not any(e["event"] in ("dry_run", "timer_fired", "timer_error") for e in events(tmp_path))


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


# --- on time: within FIRE_LATE_MAX_S of 09:30:00.000, on the last trade RECEIVED before
# --- 09:30:00.000 (the research anchor)
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


@pytest.mark.parametrize("us, late", [(0, False), (1000, True)])
def test_the_grace_ends_at_exactly_fire_late_max_s(tmp_path, us, late):
    """09:30:01.000 is still on time (the pre-open anchor); 09:30:01.001 is late (the latest)."""
    assert FIRE_LATE_MAX_S == 1.0
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 29, 59, 980000), 24500.0)
    md.push("NQ", et(9, 30, 0, 900000), 24512.0)
    at(clock, 9, 30, 1, us); run(timer.tick())
    assert fired(tmp_path) == [("nq930", late, round(1 + us / 1e6, 3), "late_fire" if late else None,
                                "current" if late else "pre_open", 24512.0 if late else 24500.0)]


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
    assert stamps(fired) == {
        "anchor_seen": "09:29:59.990", "anchor_stamp_raw": "2026-09-14T13:29:59.960Z",
        "anchor_stamp": "09:29:59.960", "anchor_lag_ms": 30,
        "newest_seen": "09:30:00.300", "newest_stamp_raw": "1789392600258",
        "newest_stamp": "09:30:00.258", "newest_lag_ms": 42}
    assert (fired["anchor"], fired["anchor_source"]) == (24500.0, "pre_open")


def test_on_time_with_no_pre_open_trade_it_fires_on_the_first_trade_after_the_open(tmp_path):
    """The first print arrives after the open; the fire, still on time, has no pre-open
    trade to anchor on: it fires on that print -- off the pre-open anchor, and said so."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 30, 0, 100000), 24511.0, stamp=None)
    at(clock, 9, 30, 0, 200000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", False, 0.2, "no_pre_open_quote", "current", 24511.0)]
    e = next(e for e in events(tmp_path) if e["event"] == "timer_fired")
    assert stamps(e) == {
        "anchor_seen": "09:30:00.100", "anchor_stamp_raw": None, "anchor_stamp": None, "anchor_lag_ms": None,
        "newest_seen": "09:30:00.100", "newest_stamp_raw": None, "newest_stamp": None,
        "newest_lag_ms": None}
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["anchor_source"], st["reason"]) == ("fired", "current", "no_pre_open_quote")


def _bid_only(md, symbol, seen):
    """A quote push with no trade in it (the bid moved), received at `seen`."""
    cid = next(c for c, s in md._cid_sym.items() if s == symbol)
    md._received = seen.timestamp()
    md._on_event({"e": "md", "d": {"quotes": [
        {"contractId": cid, "entries": {"Bid": {"price": 24499.75, "size": 3}}}]}})


def waits(root):
    """timer_waiting lines: (reason, text, pushes, age_s, late)."""
    return [(e["reason"], e["text"], e["pushes"], e.get("age_s"), e["late"])
            for e in events(root) if e["event"] == "timer_waiting"]


def _staged(root):
    root.mkdir()
    timer, engine, md, clock = mk(root, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())
    return timer, md, clock


def test_no_fresh_trade_waits_and_says_which_it_is_with_the_push_count(tmp_path):
    """Review 2026-09-28: one text covered five causes; G: none of them is final any more.
    With no fresh trade at all it waits -- no push at all, pushes without a trade, or the
    newest trade too old (its age) -- one timer_waiting line, the status saying why."""
    timer, md, clock = _staged(tmp_path / "none")
    at(clock, 9, 30); run(timer.tick())
    assert waits(tmp_path / "none") == [("no_pushes", "no quote pushes at all for NQ", 0, None, False)]
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["wait_reason"], st["wait_text"], st["wait_late_s"]) ==         ("waiting", "no_pushes", "no quote pushes at all for NQ", 0.0)

    timer, md, clock = _staged(tmp_path / "no-trade")
    _bid_only(md, "NQ", et(9, 29, 59, 500000))
    _bid_only(md, "NQ", et(9, 29, 59, 700000))
    at(clock, 9, 30); run(timer.tick())
    assert waits(tmp_path / "no-trade") == [("no_trade", "none of 2 quote pushes for NQ had a trade", 2, None, False)]

    timer, md, clock = _staged(tmp_path / "stale")
    md.push("NQ", et(9, 29, 40), 24500.0)                        # 20 s before the fire
    at(clock, 9, 30); run(timer.tick())
    assert waits(tmp_path / "stale") == [
        ("stale_trade", "newest trade is 20.0 s old (1 quote push, NQ)", 1, 20.0, False)]
    assert not any(e["event"] in ("timer_error", "timer_fired") for e in events(tmp_path / "stale"))


def test_a_wait_that_starts_late_keeps_why_it_was_late(tmp_path):
    root = tmp_path / "stall"
    timer, md, clock = _staged(root)
    md.push("NQ", et(9, 30, 30), 24520.0)
    _bid_only(md, "NQ", et(9, 30, 59))
    at(clock, 9, 31); run(timer.tick())                          # the loop stalled a minute
    assert waits(root) == [("stale_trade", "newest trade is 30.0 s old (2 quote pushes, NQ)", 2, 30.0, True)]
    assert next(e for e in events(root) if e["event"] == "timer_waiting")["late_reason"] == "late_fire"
    md.push("NQ", et(9, 31, 1), 24530.0)
    at(clock, 9, 31, 1, 200000); run(timer.tick())
    assert fired(root) == [("nq930", True, 61.2, "late_fire", "current", 24530.0)]
    e = next(e for e in events(root) if e["event"] == "timer_fired")
    assert (e["waited_s"], e["wait_reason"]) == (1.2, "stale_trade")


def test_the_status_follows_the_waits_cause_without_journaling_it(tmp_path):
    timer, md, clock = _staged(tmp_path / "t")
    at(clock, 9, 30); run(timer.tick())                          # no push at all
    _bid_only(md, "NQ", et(9, 30, 0, 300000))
    at(clock, 9, 30, 0, 400000); run(timer.tick())               # pushes now, still no trade
    st = timer.status()["strategies"]["nq930"]
    assert (st["wait_reason"], st["wait_text"]) == ("no_trade", "none of 1 quote push for NQ had a trade")
    assert [w[0] for w in waits(tmp_path / "t")] == ["no_pushes"]


def fired(root):
    """timer_fired lines: (strategy, late, late_s, reason, anchor_source, anchor)."""
    return [(e["strategy"], e["late"], e["late_s"], e.get("reason"), e["anchor_source"], e["anchor"])
            for e in events(root) if e["event"] == "timer_fired"]


# --- the account holder's rule (2026-09-28): a LATE fire still fires, while the accept window
# --- is open, on the latest trade at that moment -- journaled late, with why
@pytest.mark.parametrize("hms", [(9, 30, 2), (9, 37, 0), (9, 44, 59)])
def test_a_restart_after_the_grace_fires_late_on_the_price_at_that_moment(tmp_path, hms):
    """The desk (re)starts after the open on a day it has not traded: it gates and stages as
    ever and fires, the window still open, on the latest trade -- both stops offset_pts either
    side of the current price. A fresh md has no pre-open print at all."""
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24619.0}))
    at(clock, *hms); run(timer.tick())                           # a fresh SelfTimer = a restart
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["anchor"] == 24619.0
    assert [(b.side, b.price) for b in engine.adapters["main"].brackets] == \
        [("Buy", 24629.0), ("Sell", 24609.0)]
    late_s = (hms[1] - 30) * 60 + hms[2]
    assert fired(tmp_path) == [("nq930", True, late_s, "late_start", "current", 24619.0)]
    ev = next(e for e in events(tmp_path) if e["event"] == "timer_fired")
    assert ev["anchor_seen"] == ev["newest_seen"] == "%02d:%02d:%02d.000" % hms
    at(clock, *hms, 500000); run(timer.tick())                   # the next tick: fired once
    assert len(fired(tmp_path)) == 1
    assert not any(e["event"] == "timer_missed" for e in events(tmp_path))


def test_a_staged_strategy_whose_tick_wakes_past_the_grace_fires_late_on_the_current_price(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged in time
    md.push("NQ", et(9, 29, 59, 990000), 24500.0)               # the pre-open print: not the anchor now
    md.push("NQ", et(9, 30, 2, 800000), 24531.0)
    at(clock, 9, 30, 3); run(timer.tick())                       # ... but the loop stalled 3 s
    assert fired(tmp_path) == [("nq930", True, 3.0, "late_fire", "current", 24531.0)]
    assert [(b.side, b.price) for b in engine.adapters["main"].brackets] == \
        [("Buy", 24541.0), ("Sell", 24521.0)]


def test_seen_before_the_open_but_staged_after_it_fires_late_as_a_late_stage(tmp_path):
    """First seen at 09:29:59.9; its gate's daily bars take 2 s, so it stages at 09:30:01.9
    and the next tick fires it -- late, on the price then: late_stage, not a late tick."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD(snapshot={"NQ": 24520.0}))
    bars = md.daily_bars

    async def slow_bars(symbol, n=60):
        clock.dt += dt.timedelta(seconds=2)
        return await bars(symbol, n)

    md.daily_bars = slow_bars
    at(clock, 9, 29, 59, 900000); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["seen_at"], st["staged_at"]) == ("staged", "09:29:59.900", "09:30:01.900")
    at(clock, 9, 30, 2); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 2.0, "late_stage", "current", 24520.0)]
    assert [(e["upper"], e["lower"]) for e in events(tmp_path) if e["event"] == "dry_run"] == \
        [(24530.0, 24510.0)]


def test_switched_on_after_the_open_fires_late_and_the_on_time_one_stays_pre_open(tmp_path):
    timer, engine, md, clock = mk(tmp_path, md=TapeMD(snapshot={"YM": 46050.0}))
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # nq930 staged
    md.push("NQ", et(9, 29, 59, 990000), 24500.0)
    md.push("NQ", et(9, 30, 0, 100000), 24511.0)                 # after the open
    at(clock, 9, 30); run(timer.tick())                          # nq930 fires on time
    _add_ym(engine)                                              # ym930 switched on at 09:33
    at(clock, 9, 33); run(timer.tick())
    assert fired(tmp_path) == [("nq930", False, 0.0, None, "pre_open", 24500.0),
                               ("ym930", True, 180.0, "late_switch_on", "current", 46050.0)]


def test_after_the_accept_window_a_late_start_still_never_fires(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24619.0}))
    at(clock, 9, 45, 1); run(timer.tick())                       # the window closed at 09:45:00
    assert timer.status()["strategies"]["nq930"]["stage"] == "missed"
    assert md.subs == [] and engine.adapters["main"].brackets == []
    ev = events(tmp_path)
    assert [e["window_end"] for e in ev if e["event"] == "timer_missed"] == ["09:45"]
    assert not any(e["event"] in ("timer_fired", "dry_run", "placed") for e in ev)


# --- loud: a late fire and a miss are kept in the timer status, with why (the pill, readiness)
def test_the_status_keeps_a_fires_lateness_and_why(tmp_path):
    timer, engine, md, clock = mk(tmp_path, md=TapeMD(snapshot={"NQ": 24619.0}))
    at(clock, 9, 31, 4, 250000); run(timer.tick())               # a restart at 09:31:04.25
    st = timer.status()["strategies"]["nq930"]
    assert {k: st[k] for k in ("stage", "anchor", "late", "late_s", "reason")} == \
        {"stage": "fired", "anchor": 24619.0, "late": True, "late_s": 64.25, "reason": "late_start"}

    root = tmp_path / "on-time"
    root.mkdir()
    timer, engine, md, clock = mk(root)
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["late"], st["late_s"], "reason" in st) == ("fired", False, 0.0, False)


def _missed(root):
    return [(e["strategy"], e["reason"], e["late_s"], e["window_end"])
            for e in events(root) if e["event"] == "timer_missed"]


def test_a_missed_window_says_why_in_the_status_and_the_journal_once_a_day(tmp_path):
    """The desk down through the accept window: missed, with why (late_start: it came up after
    the window) and late_s -- journaled ONCE, however often it restarts that day."""
    for hh, mm in ((11, 0), (14, 19), (23, 3)):                  # three restarts, one day
        timer, engine, md, clock = mk(tmp_path, armed=True)
        at(clock, hh, mm); run(timer.tick())
        st = timer.status()["strategies"]["nq930"]
        assert (st["stage"], st["reason"], st["late_s"]) == ("missed", "late_start", 5400.0), (hh, mm)
    assert _missed(tmp_path) == [("nq930", "late_start", 5400.0, "09:45")]
    assert md.subs == [] and engine.adapters["main"].brackets == []


def test_a_miss_says_whether_it_was_switched_on_late_or_never_reached_in_time(tmp_path):
    timer, engine, md, clock = mk(tmp_path)
    at(clock, 9, 21); run(timer.tick())                          # nq930 gated
    _add_ym(engine)                                              # ym930 switched on at 10:00
    at(clock, 10, 0); run(timer.tick())                          # nq930: the loop stalled 09:21 -> 10:00
    st = timer.status()["strategies"]
    assert (st["nq930"]["stage"], st["nq930"]["reason"]) == ("missed", "window_closed")
    assert (st["ym930"]["stage"], st["ym930"]["reason"]) == ("missed", "late_switch_on")
    assert sorted(_missed(tmp_path)) == [("nq930", "window_closed", 1800.0, "09:45"),
                                         ("ym930", "late_switch_on", 1800.0, "09:45")]


@pytest.mark.parametrize("status", ["placed", "live", "done"])
def test_a_restart_after_the_window_on_a_day_that_acted_is_done_not_missed(tmp_path, status):
    """Live 2026-09-28: nq930 fired at 09:30, the desk restarted at 09:45:31 and journaled
    timer_missed for it. Now a problem, that would be a false alarm: it is done, quietly."""
    timer, engine, md, clock = mk(tmp_path, armed=True)
    engine._state("nq930", "main").status = status
    at(clock, 9, 45, 31); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "done"
    assert _missed(tmp_path) == [] and not any(e["event"] == "timer_deferred" for e in events(tmp_path))


def test_a_restart_after_the_window_keeps_what_the_earlier_run_decided(tmp_path):
    """A fire that placed nothing (disarmed here; live nq930_1030 has no book, so the engine
    refuses it), a chop day, an error: a restart after the window keeps what the earlier run
    decided, from today's journal -- never 'missed', nothing journaled again. A prestage's
    account-level skip decides nothing."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD(snapshot={"NQ": 24619.0}))
    at(clock, 9, 31, 4, 250000); run(timer.tick())               # nq930 fires late: a dry run
    engine.journal("timer_skipped", strategy="es930", reason="gate_chop", adx=14.24)
    engine.journal("timer_error", strategy="rty930", error="no fresh trade for the anchor")
    engine.journal("timer_skipped", strategy="cl930", reason="manual_position", account="main")
    before = len(events(tmp_path))
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())          # the desk restarts after the window
    for extra in ("es930", "rty930", "cl930"):
        timer.cfg.strategies[extra] = StrategyCfg(symbol="ES", qty=1, offset_pts=5.0, sl_pts=2.0,
                                                  tp_pts=6.0, enabled=True, self_fire=True)
    at(clock, 11, 0); run(timer.tick())
    st = timer.status()["strategies"]
    assert {k: st["nq930"][k] for k in ("stage", "anchor", "late", "late_s", "reason")} == \
        {"stage": "fired", "anchor": 24619.0, "late": True, "late_s": 64.25, "reason": "late_start"}
    assert (st["es930"]["stage"], st["es930"]["gate"], st["es930"]["adx"]) == ("skipped", False, 14.24)
    assert (st["rty930"]["stage"], st["rty930"]["error"]) == ("error", "no fresh trade for the anchor")
    assert (st["cl930"]["stage"], st["cl930"]["reason"]) == ("missed", "late_start")
    assert [(e["event"], e["strategy"]) for e in events(tmp_path)[before:]] == [("timer_missed", "cl930")]


def test_a_killed_day_after_the_window_is_skipped_not_missed(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True)
    engine.kill_today("nq930")
    at(clock, 11, 0); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["killed"]) == ("skipped", True) and _missed(tmp_path) == []


def test_a_mangled_journal_still_says_the_miss(tmp_path):
    """Bad bytes, a torn line, lines that are no object, yesterday's outcome: none decides
    today, none crashes the timer."""
    (tmp_path / "journal.jsonl").write_bytes(
        b'\xff\xfe{"et": "2026-09-14T09:30:00", "event": "timer_\n[1]\nnull\n"timer_fired"\n'
        b'{"et": "2026-09-11T09:30:00-04:00", "event": "timer_fired", "strategy": "nq930"}\n')
    timer, engine, md, clock = mk(tmp_path, armed=True)
    at(clock, 11, 0); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "missed"
    lines = (tmp_path / "journal.jsonl").read_text(errors="replace").splitlines()
    assert [json.loads(l)["reason"] for l in lines if '"timer_missed"' in l] == ["late_start"]


def test_a_late_fire_goes_out_as_its_anchor_is_read_not_behind_a_later_stage(tmp_path):
    """A restart at 09:31: nq930 gates, stages and fires late; ym930 stages after it and its
    subscription takes 1.5 s. nq930's orders are out at 09:31:00, on NQ's price then."""
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24619.0}))
    sent = []
    _slow_ym_stage(engine, md, clock, sent)
    at(clock, 9, 31); run(timer.tick())
    assert sent == [("NQ", "Buy", 24629.0, dt.time(9, 31)), ("NQ", "Sell", 24609.0, dt.time(9, 31)),
                    ("YM", "Buy", 46030.0, dt.time(9, 31, 1, 500000)),
                    ("YM", "Sell", 45990.0, dt.time(9, 31, 1, 500000))]
    assert fired(tmp_path) == [("nq930", True, 60.0, "late_start", "current", 24619.0),
                               ("ym930", True, 61.5, "late_start", "current", 46010.0)]


def _slow_ym_stage(engine, md, clock, sent):
    """ym930 switched on just before the open: its quote subscription takes 1.5 s (YM's
    print arrives as it answers). Every bracket sent is recorded with the clock's ET time."""
    _add_ym(engine)
    sub = md.subscribe_quote

    async def slow(symbol):
        out = await sub(symbol)
        if symbol == "YM":
            await asyncio.sleep(0.01)                            # a real round trip: other tasks run
            clock.dt += dt.timedelta(seconds=1.5)                # ... and it holds this tick 1.5 s
            md.push("YM", clock.dt, 46010.0)
        return out

    ad = engine.adapters["main"]
    place = ad.place_bracket

    async def timed(req):
        sent.append((req.symbol, req.side, req.price, clock.dt.astimezone(ET).time()))
        return await place(req)

    md.subscribe_quote, ad.place_bracket = slow, timed


def test_an_on_time_fire_goes_out_before_another_strategy_stages_in_its_tick(tmp_path):
    """Review 2026-09-28: nq930 checks in on time at 09:30:00.000, but ym930 -- switched on
    just before the open -- stages in the same tick, and its quote subscription takes 1.5 s.
    nq930 was staged by an earlier tick: it fires first, its orders out at 09:30:00.000 on the
    last trade received before the open, whatever ym930's stage costs. ym930, staged 1.5 s
    past the open, fires late on YM's price then."""
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # nq930 staged
    md.push("NQ", et(9, 29, 59, 990000), 24500.0)
    sent = []
    _slow_ym_stage(engine, md, clock, sent)
    at(clock, 9, 30); run(timer.tick())
    assert sent == [("NQ", "Buy", 24510.0, dt.time(9, 30)), ("NQ", "Sell", 24490.0, dt.time(9, 30)),
                    ("YM", "Buy", 46030.0, dt.time(9, 30, 1, 500000)),
                    ("YM", "Sell", 45990.0, dt.time(9, 30, 1, 500000))]
    st = timer.status()["strategies"]
    assert (st["nq930"]["stage"], st["nq930"]["anchor"]) == ("fired", 24500.0)
    assert (st["ym930"]["stage"], st["ym930"]["anchor"]) == ("fired", 46010.0)
    assert fired(tmp_path) == [("nq930", False, 0.0, None, "pre_open", 24500.0),
                               ("ym930", True, 1.5, "late_stage", "current", 46010.0)]
    assert not any(e["event"] == "timer_missed" for e in events(tmp_path))


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
    closed weekday (Christmas, a Friday) runs the weekday rules: with no trade it waits, on
    time and late alike, and the window's close says it missed -- once."""
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
    assert timer.status()["strategies"]["nq930"]["stage"] == "waiting"
    at(clock, 9, 45, 1, date=xmas); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["reason"]) == ("missed", "no_fresh_quote")
    assert [e["event"] for e in events(root) if e["event"].startswith("timer_")] == \
        ["timer_gate", "timer_waiting", "timer_missed"]

    root = tmp_path / "xmas-late"
    root.mkdir()
    timer, engine, md, clock = mk(root, md=TapeMD())             # a restart at 09:37: no print comes
    at(clock, 9, 37, date=xmas); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["wait_why"]) == ("waiting", "late_start")
    assert not any(e["event"] in ("timer_missed", "timer_fired", "timer_error", "dry_run")
                   for e in events(root))


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
    timer, engine, md, clock = mk(root, armed=True, md=TapeMD(snapshot={"NQ": 24519.0}))
    at(clock, 9, 30, 2, date=date); run(timer.tick())
    assert fired(root) == [("nq930", True, 2.0, "late_start", "current", 24519.0)]
    ev = next(e for e in events(root) if e["event"] == "timer_fired")
    assert ev["anchor_seen"] == "09:30:02.000"
    assert [(b.side, b.price) for b in engine.adapters["main"].brackets] == \
        [("Buy", 24529.0), ("Sell", 24509.0)]


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
    m._on_event({"e": "md", "d": {"quotes": [                    # no trade in it; an unknown contract
        {"contractId": 3267315, "entries": {"Bid": {"price": 24509.25, "size": 2}}},
        {"contractId": 999, "entries": {"Trade": {"price": 1.0, "size": 1}}}]}})
    assert (m.pushes("NQZ6"), m.pushes("YMZ6"), m.pushes("ESZ6")) == (5, 1, 0)   # every push, trade or not
    assert m.last("NQZ6")[0] == 24509.5
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


# --- G (the account holder, 2026-09-28: "I'd rather it fire"): an anchor that is not there
# --- YET is never final -- it waits, trying every tick, until the accept window closes
def test_a_late_start_waits_for_its_first_push_and_fires_on_it(tmp_path):
    """A restart after the open no longer needs the first quote to come with the subscribe
    reply: its first push comes 2 s after it, and it fires on that push -- late_start. One
    timer_waiting line, however many ticks it waits."""
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 31); run(timer.tick())                          # a restart: gate, subscribe, no push
    assert timer.status()["strategies"]["nq930"]["stage"] == "waiting"
    for i in range(1, 10):                                       # 09:31:00.2 .. 09:31:01.8: nothing
        at(clock, 9, 31, i // 5, i % 5 * 200000); run(timer.tick())
    md.push("NQ", et(9, 31, 2), 24619.0)
    at(clock, 9, 31, 2, 200000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 62.2, "late_start", "current", 24619.0)]
    ev = events(tmp_path)
    assert [(w["reason"], w["pushes"], w["late"], w["late_reason"]) for w in ev
            if w["event"] == "timer_waiting"] == [("no_pushes", 0, True, "late_start")]
    e = next(e for e in ev if e["event"] == "timer_fired")
    assert (e["waited_s"], e["wait_reason"]) == (2.2, "no_pushes")
    assert [(b.side, b.price) for b in engine.adapters["main"].brackets] == \
        [("Buy", 24629.0), ("Sell", 24609.0)]
    assert not any(e["event"] in ("timer_error", "timer_missed") for e in ev)


def test_a_switch_on_at_092959_9_fires_on_the_first_fresh_trade(tmp_path):
    """ym930 switched on at 09:29:59.9 stages in that tick; YM has no print yet at 09:30:00.000,
    so it waits -- and fires on YM's first trade, 0.15 s into the open: on time, off the
    pre-open anchor, said so. nq930 fires on its pre-open trade as ever."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # nq930 staged
    md.push("NQ", et(9, 29, 59, 990000), 24500.0)
    _add_ym(engine)
    at(clock, 9, 29, 59, 900000); run(timer.tick())
    assert timer.status()["strategies"]["ym930"]["stage"] == "staged"
    at(clock, 9, 30); run(timer.tick())
    assert timer.status()["strategies"]["ym930"]["stage"] == "waiting"
    md.push("YM", et(9, 30, 0, 150000), 46012.0)
    at(clock, 9, 30, 0, 200000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", False, 0.0, None, "pre_open", 24500.0),
                               ("ym930", False, 0.2, "waited_for_quote", "current", 46012.0)]
    assert [(e["strategy"], e["reason"]) for e in events(tmp_path) if e["event"] == "timer_waiting"] == \
        [("ym930", "no_pushes")]
    assert [(e["upper"], e["lower"]) for e in events(tmp_path)
            if e["event"] == "dry_run" and e["strategy"] == "ym930"] == [(46032.0, 45992.0)]


def test_a_dead_feed_that_recovers_at_0940_fires_then(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # staged
    md.push("NQ", et(9, 29, 30), 24500.0)                        # then silence: 30 s old at the open
    at(clock, 9, 30); run(timer.tick())
    for mm in range(30, 40):                                     # ten minutes of ticks, nothing new
        at(clock, 9, mm, 30); run(timer.tick())
    assert engine.adapters["main"].brackets == []
    md.push("NQ", et(9, 40), 24561.0)
    at(clock, 9, 40, 0, 200000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 600.2, "waited_for_quote", "current", 24561.0)]
    assert waits(tmp_path) == [("stale_trade", "newest trade is 30.0 s old (1 quote push, NQ)",
                                1, 30.0, False)]
    assert next(e for e in events(tmp_path) if e["event"] == "timer_fired")["waited_s"] == 600.2
    assert [(b.side, b.price) for b in engine.adapters["main"].brackets] == \
        [("Buy", 24571.0), ("Sell", 24551.0)]


def test_a_feed_that_never_recovers_is_missed_once_when_the_window_closes(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())
    at(clock, 9, 30); run(timer.tick())                          # nothing at all: it waits
    for mm in range(31, 46):
        at(clock, 9, mm); run(timer.tick())                      # 09:45:00 is still the window
    assert timer.status()["strategies"]["nq930"]["stage"] == "waiting"
    at(clock, 9, 45, 0, 200000); run(timer.tick())               # closed
    for hh, mm in ((9, 50), (10, 30), (15, 0)):
        at(clock, hh, mm); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["reason"], st["late_s"]) == ("missed", "no_fresh_quote", 900.2)
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())   # and a restart at 11:00
    at(clock, 11, 0); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["reason"] == "no_fresh_quote"
    ev = [e for e in events(tmp_path) if e["event"] in ("timer_waiting", "timer_missed",
                                                        "timer_error", "timer_fired")]
    assert [(e["event"], e["reason"]) for e in ev] == \
        [("timer_waiting", "no_pushes"), ("timer_missed", "no_fresh_quote")]
    assert (ev[1]["wait_reason"], ev[1]["text"], ev[1]["waited_s"], ev[1]["window_end"]) == \
        ("no_pushes", "no quote pushes at all for NQ", 900.2, "09:45")
    assert engine.adapters["main"].brackets == []


# --- one fire a day, whatever overlaps a wait -------------------------------------------------
def _waiting(root, **kw):
    timer, engine, md, clock = mk(root, armed=True, md=TapeMD(), **kw)
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())
    at(clock, 9, 30); run(timer.tick())                          # no quote: it waits
    assert timer.status()["strategies"]["nq930"]["stage"] == "waiting"
    return timer, engine, md, clock


def test_a_wait_never_fires_on_a_day_the_tv_alert_placed(tmp_path):
    timer, engine, md, clock = _waiting(tmp_path)
    at(clock, 9, 30, 5)
    assert run(engine.handle_alert({"strategy": "nq930", "upper": 24510.0, "lower": 24490.0},
                                   source="tv"))["ok"]
    md.push("NQ", et(9, 30, 5, 500000), 24530.0)                 # a quote now -- the day acted
    for s in (6, 7, 8):
        at(clock, 9, 30, s); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "done"
    ev = events(tmp_path)
    assert [e["status"] for e in ev if e["event"] == "timer_deferred"] == ["placed"]
    assert fired(tmp_path) == []
    assert [(b.side, b.price) for b in engine.adapters["main"].brackets] == \
        [("Buy", 24510.0), ("Sell", 24490.0)]


def test_a_wait_across_restarts_fires_once(tmp_path):
    timer, engine, md, clock = _waiting(tmp_path)                # run 1 waits, then the desk restarts
    timer, engine2, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24619.0}))
    at(clock, 9, 31); run(timer.tick())                          # run 2 fires, late_start
    at(clock, 9, 31, 0, 200000); run(timer.tick())
    timer, engine3, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24650.0}))
    at(clock, 9, 32); run(timer.tick())                          # run 3: the day acted
    assert timer.status()["strategies"]["nq930"]["stage"] == "done"
    assert fired(tmp_path) == [("nq930", True, 60.0, "late_start", "current", 24619.0)]
    assert [(b.side, b.price) for b in engine2.adapters["main"].brackets] == \
        [("Buy", 24629.0), ("Sell", 24609.0)]
    assert engine.adapters["main"].brackets == engine3.adapters["main"].brackets == []


def test_a_wait_through_a_switch_off_and_on_fires_once(tmp_path):
    timer, engine, md, clock = _waiting(tmp_path)
    engine.cfg.strategies["nq930"].enabled = False               # switched off while it waits
    md.push("NQ", et(9, 30, 1, 500000), 24520.0)
    at(clock, 9, 30, 2); run(timer.tick())                       # off: nothing fires
    assert fired(tmp_path) == []
    engine.cfg.strategies["nq930"].enabled = True
    at(clock, 9, 30, 2, 200000); run(timer.tick())               # on again: it fires on that quote
    for s in (3, 4):                                             # off and on again: nothing more
        engine.cfg.strategies["nq930"].enabled = s == 4
        md.push("NQ", et(9, 30, s), 24525.0)
        at(clock, 9, 30, s, 100000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 2.2, "waited_for_quote", "current", 24520.0)]
    assert len(engine.adapters["main"].brackets) == 2


def test_a_restart_never_fires_a_second_time_even_journal_only(tmp_path):
    """Disarmed, a fire leaves no day state: a restart used to fire a second dry run. The
    journal says it fired: the restarted desk keeps that, and never fires again."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())
    md.push("NQ", et(9, 29, 59, 990000), 24500.0)
    at(clock, 9, 30); run(timer.tick())                          # fires: a dry run
    timer, engine, md, clock = mk(tmp_path, md=TapeMD(snapshot={"NQ": 24619.0}))
    at(clock, 9, 31); run(timer.tick())
    at(clock, 9, 31, 0, 200000); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["anchor"], st["anchor_source"]) == ("fired", 24500.0, "pre_open")
    assert fired(tmp_path) == [("nq930", False, 0.0, None, "pre_open", 24500.0)]
    assert sum(e["event"] == "dry_run" for e in events(tmp_path)) == 1


def test_a_kill_while_waiting_ends_the_wait_and_it_never_fires(tmp_path):
    timer, engine, md, clock = _waiting(tmp_path)
    engine.kill_today("nq930")
    at(clock, 9, 30, 1); run(timer.tick())
    md.push("NQ", et(9, 30, 1, 500000), 24520.0)
    at(clock, 9, 30, 2); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["killed"]) == ("skipped", True)
    assert fired(tmp_path) == [] and engine.adapters["main"].brackets == []


def test_a_fired_strategy_never_unsubscribes_a_quote_another_still_waits_on(tmp_path):
    """09:31 unsubscribes a fired strategy's quote -- not while another strategy on the same
    symbol is still waiting on it."""
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())                          # nq930 staged
    md.push("NQ", et(9, 29, 59, 990000), 24500.0)
    at(clock, 9, 30); run(timer.tick())                          # nq930 fires
    engine.cfg.strategies["nq930b"] = StrategyCfg(
        symbol="NQ", qty=1, offset_pts=20.0, sl_pts=5.0, tp_pts=15.0, enabled=True, self_fire=True)
    engine.cfg.book["nq930b"] = [{"account": "main", "qty": 1}]
    at(clock, 9, 30, 30); run(timer.tick())                      # switched on: NQ's print is 30 s old
    assert timer.status()["strategies"]["nq930b"]["stage"] == "waiting"
    at(clock, 9, 31); run(timer.tick())                          # 09:31: nq930 is done with NQ...
    assert md.subs == ["NQ"]                                     # ... but nq930b is not
    md.push("NQ", et(9, 31, 30), 24533.0)
    at(clock, 9, 31, 30, 200000); run(timer.tick())
    assert fired(tmp_path)[-1] == ("nq930b", True, 90.2, "late_switch_on", "current", 24533.0)
    at(clock, 9, 31, 31); run(timer.tick())                      # now nobody needs it
    assert md.subs == []


def test_a_failed_waiting_line_never_ends_the_wait(tmp_path, monkeypatch):
    real = Engine.journal

    def flaky(self, event, **data):
        if event == "timer_waiting":
            raise OSError("disk full")
        return real(self, event, **data)

    monkeypatch.setattr(Engine, "journal", flaky)
    timer, engine, md, clock = _waiting(tmp_path)                # the line failed; still waiting
    md.push("NQ", et(9, 30, 1), 24520.0)
    at(clock, 9, 30, 1, 200000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 1.2, "waited_for_quote", "current", 24520.0)]


# --- review round 2: a late fire needs its accounts connected and synced, and never twice ---
class ViewAdapter(FakeAdapter):
    """A FakeAdapter with the real adapter's cached view (trade_view): what the prestage reads."""

    def __init__(self, aid, orders=(), positions=(), seeded=True, connected=True):
        super().__init__(aid)
        self.view = {"orders": list(orders), "positions": list(positions), "seeded": seeded}
        self._connected = connected

    def trade_view(self):
        return self.view


def test_a_restart_while_the_fires_orders_are_in_flight_never_places_again(tmp_path):
    """Round 2, R1: the legs reached the broker and the desk died before the acks. "placing"
    is saved before the legs go out, so the restarted desk sees a day that acted."""
    loop = asyncio.new_event_loop()
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 21); loop.run_until_complete(timer.tick())
    at(clock, 9, 29); loop.run_until_complete(timer.tick())
    md.push("NQ", et(9, 29, 59, 900000), 24500.0)
    ad = engine.adapters["main"]
    hang = asyncio.Event()

    async def sent_then_hang(req):
        ad.brackets.append(req)
        await hang.wait()

    ad.place_bracket = sent_then_hang
    at(clock, 9, 30)
    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        loop.run_until_complete(asyncio.wait_for(timer.tick(), 0.05))   # the crash
    loop.close()
    assert json.loads((tmp_path / "day-2026-09-14.json").read_text())["nq930@main"]["status"] == "placing"
    timer2, engine2, md2, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24512.0}))
    at(clock, 9, 30, 3); run(timer2.tick())
    at(clock, 9, 30, 3, 200000); run(timer2.tick())
    assert timer2.status()["strategies"]["nq930"]["stage"] == "done"
    assert engine2.adapters["main"].brackets == [] and len(ad.brackets) == 2


def test_a_late_start_waits_for_its_account_to_sync_and_skips_a_manual_position(tmp_path):
    """Round 2, R4: the desk came up at 09:31; its adapter logs in and syncs while the timer
    waits. The prestage ran before any cached view existed -- the late fire runs its cached
    half again: the manual NQ +2 skips the account, nothing is placed on top of it."""
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24520.0}))
    engine.adapters["main"] = ViewAdapter("main", seeded=False, connected=False)
    at(clock, 9, 31); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["wait_reason"]) == ("waiting", "account_down")
    engine.adapters["main"]._connected = True
    at(clock, 9, 31, 0, 200000); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["wait_reason"] == "account_unseeded"
    real = engine.adapters["main"] = ViewAdapter(
        "main", positions=[{"contract_id": 1, "symbol": "NQZ6", "net": 2}])
    md.push("NQ", et(9, 31, 0, 350000), 24521.0)
    at(clock, 9, 31, 0, 400000); run(timer.tick())
    ev = events(tmp_path)
    assert [(e["account"], e["reason"], e["net"]) for e in ev
            if e["event"] == "timer_skipped"] == [("main", "manual_position", 2)]
    assert real.brackets == [] and [w["reason"] for w in ev if w["event"] == "timer_waiting"] == \
        ["account_down"]


def test_a_late_start_whose_adapter_is_still_logging_in_waits_then_fires(tmp_path):
    """Round 2, R5: it used to fire at once -- "account not connected", the day lost."""
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24520.0}))
    engine.adapters["main"]._connected = False
    at(clock, 9, 31); run(timer.tick())
    engine.adapters["main"]._connected = True
    md.push("NQ", et(9, 31, 0, 900000), 24522.0)
    at(clock, 9, 31, 1); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 61.0, "late_start", "current", 24522.0)]
    assert engine.day_status("nq930") == "placed"
    assert not any(e["event"] == "place_failed" for e in events(tmp_path))
    e = next(e for e in events(tmp_path) if e["event"] == "timer_fired")
    assert (e["waited_s"], e["wait_reason"]) == (1.0, "account_down")


def test_an_account_booked_during_a_wait_is_checked_before_the_fire(tmp_path):
    timer, engine, md, clock = _waiting(tmp_path)                # waits: no quote
    engine.cfg.accounts["a2"] = AccountCfg(keyring_key="k", account_name="A2")
    engine.cfg.book["nq930"].append({"account": "a2", "qty": 1})
    a2 = engine.adapters["a2"] = ViewAdapter("a2", orders=[{"order_id": "9", "symbol": "NQZ6"}])
    md.push("NQ", et(9, 30, 5), 24520.0)
    at(clock, 9, 30, 5, 200000); run(timer.tick())
    assert [(e["account"], e["reason"]) for e in events(tmp_path) if e["event"] == "timer_skipped"] == \
        [("a2", "manual_order")]
    assert a2.brackets == [] and len(engine.adapters["main"].brackets) == 2


def test_the_window_closing_on_an_account_wait_says_so(tmp_path):
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD(snapshot={"NQ": 24520.0}))
    engine.adapters["main"]._connected = False
    at(clock, 9, 44); run(timer.tick())
    at(clock, 9, 45, 1); run(timer.tick())
    st = timer.status()["strategies"]["nq930"]
    assert (st["stage"], st["reason"]) == ("missed", "accounts_not_ready")


# --- review round 2, item 2: how old an anchor may be --------------------------------------
def test_a_late_fire_never_goes_out_on_a_quote_older_than_current_max_age(tmp_path):
    """R2: a stalled tick at 09:30:12 found a trade received 09:29:59.9 (12.1 s old) and
    fired on it. The late anchor must be at most CURRENT_MAX_AGE_S old: it waits."""
    from homebase.timer import CURRENT_MAX_AGE_S
    assert CURRENT_MAX_AGE_S == 1.5
    timer, engine, md, clock = mk(tmp_path, armed=True, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())
    md.push("NQ", et(9, 29, 59, 900000), 24500.0)
    at(clock, 9, 30, 12); run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "waiting"
    md.push("NQ", et(9, 30, 10, 400000), 24531.0)                # 1.6 s old at the next tick: still no
    at(clock, 9, 30, 12, 200000); run(timer.tick())
    assert fired(tmp_path) == []
    md.push("NQ", et(9, 30, 11), 24533.0)                        # 1.4 s old at 09:30:12.4: yes
    at(clock, 9, 30, 12, 400000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", True, 12.4, "late_fire", "current", 24533.0)]


@pytest.mark.parametrize("age_s, fires_pre_open", [(4.9, True), (5.1, False)])
def test_a_pre_open_trade_older_than_pre_open_max_age_means_a_dead_feed(tmp_path, age_s, fires_pre_open):
    from homebase.timer import PRE_OPEN_MAX_AGE_S
    assert PRE_OPEN_MAX_AGE_S == 5.0
    timer, engine, md, clock = mk(tmp_path, md=TapeMD())
    at(clock, 9, 21); run(timer.tick())
    at(clock, 9, 29); run(timer.tick())
    md.push("NQ", et(9, 30) - dt.timedelta(seconds=age_s), 24500.0)
    at(clock, 9, 30); run(timer.tick())
    if fires_pre_open:
        assert fired(tmp_path) == [("nq930", False, 0.0, None, "pre_open", 24500.0)]
        return
    assert timer.status()["strategies"]["nq930"]["wait_reason"] == "stale_trade"
    md.push("NQ", et(9, 30, 0, 300000), 24508.0)                 # the feed comes back after the open
    at(clock, 9, 30, 0, 400000); run(timer.tick())
    assert fired(tmp_path) == [("nq930", False, 0.4, "waited_for_quote", "current", 24508.0)]
