"""The level timer: stage -> history -> fire on the strategy's own clock, every fail-safe, the price watcher.

A fake market-data socket stands in for Tradovate's: quote pushes reach the timer through the same trade hook the
real TradovateMD calls, and the 1-minute chart history comes from the same synthetic day, so the ATR the timer
fires with can be checked against the research definition (ref_atr)."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

from homebase import leveltimer
from homebase.atrbars import et_ms
from homebase.config import AccountCfg, AppCfg
from tests.levels_util import strategy_cfg
from homebase.engine import Engine
from homebase.leveltimer import LevelTimer
from homebase.levels import straddle_geometry
from homebase.broker.base import FillEvent
from tests.test_atrbars import FIRE_NYAM, FIRE_ORB, FIRE_PM, day_minutes, ref_atr
from tests.test_engine import FakeAdapter

ET = ZoneInfo("America/New_York")


def run(coro):
    """One loop per call, closed again: a tick runs hundreds of times a test and a leaked loop is a leaked fd
    (the timer reads the journal through asyncio.to_thread, so the default executor is shut down too)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()


DAY = dt.date(2026, 9, 14)                         # a Monday
TICK = 0.25


class Clock:
    def __init__(self, date=DAY):
        self.date, self.s = date, 0.0

    def at(self, hh, mm=0, ss=0.0):
        self.s = hh * 3600 + mm * 60 + ss
        return self

    def __call__(self):
        d = dt.datetime.combine(self.date, dt.time(0), tzinfo=ET) + dt.timedelta(seconds=self.s)
        return d.astimezone(dt.timezone.utc)


class FakeMD:
    """connect / subscribe / history / last / unsubscribe, and the trade hook the timer listens on."""
    contract = "NQZ6"

    def __init__(self, clock, mins):
        self.clock, self.mins = clock, mins
        self.connected = False
        self.trade_hooks, self.subs, self.unsubs, self.history_calls, self.connects = [], [], [], 0, []
        self.fail_history = False
        self.last_px = None

    async def connect(self, allow_login=True):
        self.connects.append(allow_login)
        self.connected = True

    async def subscribe_quote(self, symbol):
        self.subs.append(symbol)
        return self.contract

    async def unsubscribe_quote(self, sub):
        self.unsubs.append(sub)

    async def minute_bars(self, symbol, n):
        self.history_calls += 1
        if self.fail_history:
            raise RuntimeError("md/getChart refused")
        base = int(dt.datetime.combine(self.clock.date, dt.time(0), tzinfo=ET).timestamp() * 1000)
        now_s = self.clock.s
        out = []
        for s, o, h, l, c in self.mins:
            if s <= now_s:                                       # the newest may still be forming
                out.append({"start_ms": base + s * 1000, "o": o, "h": h, "l": l, "c": c, "v": 4})
        return out[-n:]

    def last(self, contract):
        return (self.last_px, self.clock().timestamp()) if self.last_px is not None else (None, 0.0)

    def push(self, px, seen_s=None):
        if not self.connected:
            return                                               # a dead socket delivers nothing
        seen = self.clock().timestamp() if seen_s is None else seen_s
        for fn in self.trade_hooks:
            fn(self.contract, px, 1, seen, None)
        self.last_px = px


def strat(name="lv_atr_take", **over):
    return strategy_cfg(name, **{"enabled": True, **over})


class Rig:
    def __init__(self, tmp_path, monkeypatch, name="lv_atr_take", fire_s=FIRE_NYAM, until=None, date=DAY,
                 view=None, **over):
        monkeypatch.setattr(leveltimer.symbols, "resolve_contract", lambda s: self.front)
        self.front = "NQZ6"
        self.clock = Clock(date)
        self.name, self.fire_s = name, fire_s
        self.mins = day_minutes(13, until_s=until or fire_s)
        self.md = FakeMD(self.clock, self.mins)
        cfg = AppCfg(armed=True, accounts={"a": AccountCfg(keyring_key="k", account_name="A", paper=True)},
                     strategies={name: strat(name, **over)}, book={name: [{"account": "a", "qty": 4}]})
        self.ad = FakeAdapter("a")
        if view is not None:
            self.ad.trade_view = lambda: view
        self.eng = Engine(cfg, {"a": self.ad}, now_fn=self.clock, root=tmp_path)
        self.lt = LevelTimer(cfg, self.eng, md_factory=lambda: self.md, now_fn=self.clock)
        self.tmp = tmp_path

    def tick(self, hh, mm=0, ss=0.0):
        self.clock.at(hh, mm, ss)
        run(self.lt.tick())

    def feed(self, a_s, b_s, step=30.0, end_print=True):
        """The synthetic day's prints in [a_s, b_s), ticked every `step` seconds of simulated time."""
        t = a_s
        for s, o, h, l, c in self.mins:
            if a_s <= s < b_s:
                for off, px in ((10, o), (20, h), (30, l), (40, c)):
                    self.clock.s = s + off
                    self.md.push(px)
                if end_print:
                    self.clock.s = s + 59.5
                    self.md.push(c)
                while t < s + 60:
                    self.clock.s = t
                    run(self.lt.tick())
                    t += step

    def events(self, name=None):
        p = self.tmp / "journal.jsonl"
        rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
        return [r for r in rows if name is None or r["event"] == name]

    def day_to_the_fire(self):
        """08:55:05 stage, live prints from there, history at ~08:58, then the fire at 09:30:00.05."""
        s0 = self.fire_s - leveltimer.lead_min(self.eng.cfg.strategies[self.name]) * 60
        self.tick(*divmod(s0 + 5, 3600)[:1], *divmod(divmod(s0 + 5, 3600)[1], 60))
        self.feed(s0 + 5, self.fire_s)
        self.clock.s = self.fire_s + 0.05
        run(self.lt.tick())


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------------------------- the fire
def test_nyam_fires_at_0930_with_the_research_geometry(rig):
    rig.day_to_the_fire()
    st = rig.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "fired" and st["result"] is True and st["late"] is False
    atr, n = ref_atr(rig.mins, 30, FIRE_NYAM)
    anchor = rig.mins[-1][4]
    want = straddle_geometry(anchor, atr, 0.25, 3.0, TICK, n)
    g = st["geometry"]
    assert (g["upper"], g["lower"], g["sl_pts"], g["atr_bars"]) == (want.upper, want.lower, want.sl_pts, 19)
    assert g["atr"] == pytest.approx(atr, rel=1e-12)
    buy, sell = rig.ad.brackets
    assert (buy.price, buy.stop_price, buy.tp_price, buy.qty) == (want.upper, want.upper - want.sl_pts,
                                                                  want.upper + 19.0, 4)
    assert (sell.price, sell.stop_price, sell.tp_price) == (want.lower, want.lower + want.sl_pts, want.lower - 19.0)
    fired = rig.events("level_fired")[0]
    assert fired["result"] is True and fired["contract"] == "NQZ6" and fired["late"] is False
    assert "history" in fired["coverage"]
    assert rig.events("level_staged")[0]["contract"] == "NQZ6"
    assert rig.md.history_calls >= 1 and rig.md.subs == ["NQ"]


def test_it_fires_once(rig):
    rig.day_to_the_fire()
    n = len(rig.ad.brackets)
    rig.tick(9, 30, 5)
    rig.tick(9, 30, 30)
    assert len(rig.ad.brackets) == n and len(rig.events("level_fired")) == 1


def test_the_orb_fires_at_1105_from_the_five_minute_range(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch, "lv_orb", fire_s=FIRE_ORB)
    r.day_to_the_fire()
    st = r.lt.status()["strategies"]["lv_orb"]
    assert st["stage"] == "fired" and st["result"] is True
    hi = max(m[2] for m in r.mins if FIRE_ORB - 300 <= m[0] < FIRE_ORB)
    lo = min(m[3] for m in r.mins if FIRE_ORB - 300 <= m[0] < FIRE_ORB)
    buy, sell = r.ad.brackets
    assert (buy.price, sell.price) == (hi + TICK, lo - TICK)
    assert st["geometry"]["atr_bars"] == 133
    assert buy.tp_price - buy.price == 12.75                  # day_take $1,000 net, 4 NQ
    assert r.events("level_staged")[0]["fire"] == "11:05:00"


def test_the_pm_straddle_fires_at_1330_with_its_tier_size(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch, "lv_atr_tiers", fire_s=FIRE_PM)
    r.day_to_the_fire()
    assert r.lt.status()["strategies"]["lv_atr_tiers"]["stage"] == "fired"
    buy, sell = r.ad.brackets
    assert buy.qty == 2 and buy.tp_price - buy.price == 15.25         # no standing: the smallest size, $600 net
    atr, _ = ref_atr(r.mins, 30, FIRE_PM)
    assert buy.price - r.mins[-1][4] == pytest.approx(atr, abs=TICK / 2 + 1e-9)    # +1.0 ATR


# --------------------------------------------------------------------------------------------- fail-safes
def test_no_history_means_no_fire_and_a_missed_day(rig):
    rig.md.fail_history = True
    rig.day_to_the_fire()
    assert rig.lt.status()["strategies"]["lv_atr_take"]["stage"] == "waiting"
    assert rig.ad.brackets == [] and rig.events("level_history_error")
    rig.tick(9, 31, 1)                                          # the accept window (09:29-09:31) is over
    st = rig.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "missed" and "no coverage" in st["reason"]
    assert rig.events("level_missed")


def test_a_feed_that_dropped_reads_history_again_and_closes_the_hole(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    r.feed(8 * 3600 + 55 * 60 + 5, 9 * 3600 + 10 * 60)
    r.md.connected = False                                       # the socket dies at 09:10 ...
    r.tick(9, 12, 0.5)                                           # ... and is rebuilt at 09:12: continuity restarts here
    r.feed(9 * 3600 + 12 * 60, FIRE_NYAM)                        # (the history read a minute later closes 09:10-09:12)
    r.clock.s = FIRE_NYAM + 0.05
    run(r.lt.tick())
    st = r.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "fired" and len(r.md.subs) == 2        # subscribed again on the new socket
    atr, _ = ref_atr(r.mins, 30, FIRE_NYAM)
    assert st["geometry"]["atr"] == pytest.approx(atr, rel=1e-12)    # the missed minutes are in it, from the history


def test_a_live_feed_that_went_silent_reads_history_again_and_fires(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    r.feed(8 * 3600 + 55 * 60 + 5, 9 * 3600 + 10 * 60)
    r.feed(9 * 3600 + 14 * 60, FIRE_NYAM)                        # connected, but nothing printed 09:10-09:14
    r.clock.s = FIRE_NYAM + 0.05
    run(r.lt.tick())
    st = r.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "fired" and r.md.history_calls >= 2        # the 08:58 read, and another after the silence
    assert r.lt._bars["NQ"].live_gaps                             # the silence was seen ...
    atr, _ = ref_atr(r.mins, 30, FIRE_NYAM)
    assert st["geometry"]["atr"] == pytest.approx(atr, rel=1e-12)    # ... and the minutes in it came from the history


def test_a_hole_the_history_cannot_close_is_refused(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    r.feed(8 * 3600 + 55 * 60 + 5, 9 * 3600 + 10 * 60)
    r.md.connected = False
    r.md.fail_history = True                                     # and the history is refused after the reconnect
    r.tick(9, 12, 0.5)
    r.feed(9 * 3600 + 12 * 60, FIRE_NYAM)
    r.clock.s = FIRE_NYAM + 0.05
    run(r.lt.tick())
    st = r.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "waiting" and "hole" in st["wait"] and r.ad.brackets == []


def test_a_stale_feed_waits_and_a_fresh_print_inside_the_window_fires_late(rig):
    s0 = FIRE_NYAM - 35 * 60
    rig.tick(8, 55, 5)
    rig.feed(s0 + 5, FIRE_NYAM, end_print=False)                 # the last print is 20 s before the fire
    rig.clock.s = FIRE_NYAM + 0.05
    run(rig.lt.tick())
    st = rig.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "waiting" and st["wait"] == "no fresh print" and rig.ad.brackets == []
    rig.clock.s = FIRE_NYAM + 12
    rig.md.push(rig.mins[-1][4] + 1.0)
    run(rig.lt.tick())
    st = rig.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "fired" and st["late"] is True and st["late_s"] == 12.0
    assert st["geometry"]["anchor"] == rig.mins[-1][4] + 1.0       # a late fire sits around the market as it is


def test_a_roll_between_the_stage_and_the_fire_skips(rig):
    rig.tick(8, 55, 5)
    rig.feed(FIRE_NYAM - 35 * 60 + 5, FIRE_NYAM)
    rig.front = "NQH7"                                           # the front month moved: orders would be on another contract
    rig.clock.s = FIRE_NYAM + 0.05
    run(rig.lt.tick())
    assert rig.lt.status()["strategies"]["lv_atr_take"]["reason"] == "contract_changed"
    assert rig.ad.brackets == []


def test_a_half_day_never_stages(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch, "lv_atr_tiers", fire_s=FIRE_PM, date=dt.date(2026, 11, 27))
    r.tick(12, 55, 5)
    st = r.lt.status()["strategies"]["lv_atr_tiers"]
    assert st["stage"] == "skipped" and st["reason"] == "early_close"
    assert r.md.subs == [] and r.md.connects == []
    assert r.events("level_skipped")[0]["date"] == "2026-11-27"


def test_a_killed_strategy_is_not_fired(rig):
    run(rig.eng.kill_strategy("lv_atr_take"))
    rig.day_to_the_fire()
    assert rig.lt.status()["strategies"]["lv_atr_take"]["reason"] == "killed" and rig.ad.brackets == []


def test_a_day_that_already_acted_is_deferred(rig):
    rig.eng._state("lv_atr_take", "a").status = "done"
    rig.tick(8, 55, 5)
    assert rig.lt.status()["strategies"]["lv_atr_take"]["stage"] == "done" and rig.md.subs == []


def test_a_restart_after_the_fire_does_not_fire_again(rig, tmp_path, monkeypatch):
    rig.day_to_the_fire()
    n = len(rig.ad.brackets)
    again = LevelTimer(rig.eng.cfg, Engine(rig.eng.cfg, {"a": FakeAdapter("a")}, now_fn=rig.clock, root=tmp_path),
                       md_factory=lambda: rig.md, now_fn=rig.clock)
    rig.clock.at(9, 30, 20)
    run(again.tick())
    assert again.status()["strategies"]["lv_atr_take"]["stage"] == "done"
    assert len(rig.ad.brackets) == n


def test_a_desk_that_starts_after_the_window_misses_the_day_once(rig):
    rig.tick(10, 0, 0)
    st = rig.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "missed"
    assert len(rig.events("level_missed")) == 1
    rig.tick(10, 0, 5)
    assert len(rig.events("level_missed")) == 1 and rig.md.subs == []


def test_no_market_data_request_in_the_quiet_window(tmp_path, monkeypatch):
    """09:20-09:35: no history read, and a (re)connect never takes the password login."""
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    r.md.connected = False                                       # the socket died before the quiet window
    r.md.fail_history = False
    n = r.md.history_calls
    r.tick(9, 25, 0)
    assert r.md.history_calls == n                               # no read at 09:25 ...
    assert len(r.md.connects) == 2 and set(r.md.connects) == {False}     # ... and the rebuild never takes a password login


def test_a_weekend_does_nothing(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch, date=dt.date(2026, 9, 12))
    r.tick(8, 55, 5)
    assert r.md.subs == [] and r.lt.days == {}


def test_a_manual_position_skips_the_account(tmp_path, monkeypatch):
    view = {"seeded": True, "orders": [], "positions": [{"symbol": "NQZ6", "net": 2}]}
    r = Rig(tmp_path, monkeypatch, view=view)
    r.day_to_the_fire()
    assert r.ad.brackets == []
    assert r.events("timer_skipped")[0]["reason"] == "manual_position"
    assert r.lt.status()["strategies"]["lv_atr_take"]["result"] is False


def test_an_unsynced_view_is_unknown_never_flat(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch, view={"seeded": False, "orders": [], "positions": []})
    r.day_to_the_fire()
    assert r.ad.brackets == [] and r.events("timer_skipped")[0]["reason"] == "view_unsynced"


def test_the_desks_own_orders_are_not_a_manual_order(tmp_path, monkeypatch):
    """The prestage of a second strategy on the account must not read the first one's brackets as manual."""
    view = {"seeded": True, "orders": [{"symbol": "NQZ6", "order_id": "a-101"}], "positions": []}
    r = Rig(tmp_path, monkeypatch, view=view)
    st = r.eng._state("other", "a")
    st.upper_id = "a-101"
    r.lt._manual_skips("lv_atr_take", r.eng.cfg.strategies["lv_atr_take"])
    assert r.eng.skipped_today("lv_atr_take") == set()


# -------------------------------------------------------------------------- the price watcher + the audit
def test_the_watcher_market_flattens_a_take_the_limit_missed_and_the_quote_is_kept_for_it(rig):
    rig.day_to_the_fire()
    st = rig.eng._state("lv_atr_take", "a")
    up = st.upper_px
    run(rig.eng.on_fill(FillEvent(account_id="a", symbol="NQZ6", side="Buy", qty=4, price=up + 0.25,
                                  raw={"orderId": st.upper_id})))
    assert st.status == "live" and st.take_px == up + 0.25 + 19.0
    rig.ad.net = 4
    mono = {"t": 50.0}
    rig.eng._mono = lambda: mono["t"]
    rig.clock.at(9, 40, 0)                                       # after the quiet window
    rig.md.last_px = st.take_px
    run(rig.lt.tick())                                           # touched: the grace starts
    assert rig.md.unsubs == [] and rig.ad.orders == []           # the quote is kept while a trade is open
    mono["t"] += 3.0
    run(rig.lt.tick())
    assert [o.order_type for o in rig.ad.orders] == ["Market"] and st.exit_reason == "day_take"
    assert rig.eng.account_locked("a") == "day_take"
    run(rig.lt.tick())                                           # nothing open, nothing left to fire: let go
    assert rig.md.unsubs == ["NQZ6"]


def test_a_desk_restarted_mid_trade_watches_the_take_again(rig, tmp_path):
    rig.day_to_the_fire()
    st = rig.eng._state("lv_atr_take", "a")
    run(rig.eng.on_fill(FillEvent(account_id="a", symbol="NQZ6", side="Buy", qty=4, price=st.upper_px + 0.25,
                                  raw={"orderId": st.upper_id})))
    take = st.take_px
    ad2 = FakeAdapter("a")
    ad2.net = 4
    eng2 = Engine(rig.eng.cfg, {"a": ad2}, now_fn=rig.clock, root=tmp_path)           # the restarted desk reads the day file
    mono = {"t": 10.0}
    eng2._mono = lambda: mono["t"]
    md2 = FakeMD(rig.clock, rig.mins)
    lt2 = LevelTimer(eng2.cfg, eng2, md_factory=lambda: md2, now_fn=rig.clock)
    assert eng2._state("lv_atr_take", "a").status == "live"
    rig.clock.at(9, 40, 0)
    md2.last_px = take
    run(lt2.tick())                                              # stage "done" (it already fired) -- but a trade is open
    assert md2.subs == ["NQ"] and lt2.status()["strategies"]["lv_atr_take"]["stage"] == "done"
    mono["t"] += 3
    run(lt2.tick())
    assert [o.order_type for o in ad2.orders] == ["Market"] and eng2.account_locked("a") == "day_take"


def test_a_stale_price_is_no_price(rig):
    rig.day_to_the_fire()
    st = rig.eng._state("lv_atr_take", "a")
    run(rig.eng.on_fill(FillEvent(account_id="a", symbol="NQZ6", side="Buy", qty=4, price=st.upper_px,
                                  raw={"orderId": st.upper_id})))
    rig.ad.net = 4
    rig.eng._mono = lambda: 99.0
    rig.clock.at(9, 40, 0)
    rig.md.last_px = st.take_px + 5
    rig.md.last = lambda c: (st.take_px + 5, rig.clock().timestamp() - 60)      # the newest print is a minute old
    run(rig.lt.tick())
    run(rig.lt.tick())
    assert rig.ad.orders == [] and st.status == "live"


def test_the_atr_audit_compares_the_exact_bars_after_the_fire(rig):
    rig.day_to_the_fire()
    rig.clock.at(9, 31, 0)
    run(rig.lt.tick())
    assert rig.events("level_atr_parity") == []                  # inside the quiet window: no md request
    rig.clock.at(9, 36, 0)
    run(rig.lt.tick())
    p, = rig.events("level_atr_parity")
    assert p["differs"] is False and p["bars"] == 19 and p["used"] == pytest.approx(p["exact"])
    run(rig.lt.tick())
    assert len(rig.events("level_atr_parity")) == 1               # once


def test_the_audit_says_when_a_quote_feed_coalesced_a_print(tmp_path, monkeypatch):
    """The live feed never saw a spike the chart history has: the fire used the live-built minute, the audit
    reads the exact bars, corrects the minute and says the ATR differed."""
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    spike_s = 9 * 3600 + 12 * 60
    live = list(r.mins)
    r.md.mins = [(s, o, (h + 500.0 if s == spike_s else h), l, c) for s, o, h, l, c in live]    # exact: with the spike
    r.feed(8 * 3600 + 55 * 60 + 5, FIRE_NYAM)
    r.clock.s = FIRE_NYAM + 0.05
    run(r.lt.tick())
    st = r.lt.status()["strategies"]["lv_atr_take"]
    assert st["stage"] == "fired"
    r.clock.at(9, 36, 0)
    run(r.lt.tick())
    p, = r.events("level_atr_parity")
    assert p["differs"] is True and p["minutes_corrected"] >= 1 and p["exact"] > p["used"]


def test_a_stage_that_fails_is_tried_again_not_ended(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    real, calls = r.md.subscribe_quote, {"n": 0}

    async def flaky(symbol):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("subscribeQuote refused")
        return await real(symbol)

    r.md.subscribe_quote = flaky
    r.tick(8, 55, 5)
    assert r.lt.status()["strategies"]["lv_atr_take"]["stage"] == "idle"          # not "error": no day lost to one refusal
    r.tick(8, 55, 6)
    r.tick(8, 55, 7)
    assert r.lt.status()["strategies"]["lv_atr_take"]["stage"] == "live" and r.md.subs == ["NQ"]
    assert len(r.events("level_error")) == 1                                       # said once, not on every 0.2 s tick


def test_a_new_day_subscribes_again_and_lets_go_of_yesterdays_quote(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    assert r.md.subs == ["NQ"]
    r.clock.date = dt.date(2026, 9, 15)                                            # the desk ran overnight
    r.tick(8, 55, 5)
    assert r.md.subs == ["NQ", "NQ"] and r.md.unsubs == ["NQZ6"]
    assert r.lt.status()["date"] == "2026-09-15"
    r.feed(8 * 3600 + 55 * 60 + 5, 9 * 3600)
    assert r.lt._bars["NQ"].ticks > 0 and r.lt._bars["NQ"].date == dt.date(2026, 9, 15)
