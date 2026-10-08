"""Release rehearsal 2026-10-01: a whole desk day, fake broker + fake clock + fake market data, no IO outside tmp_path.

Two days through the REAL SelfTimer (gc_nfp), LevelTimer (the four NQ "levels" algos, as reference configs:
the desk no longer ships them), Engine and
inactive sweep, ticked every few seconds of simulated time from 07:50 to 16:00 ET:

  * Fri 2026-10-02 (NFP): gc_nfp fires at 08:29:59 -- not a second before -- on its two booked accounts, and a
    fill moves its brackets to the fill; the NQ algos run their normal day beside it.
  * Mon 2026-10-05: gc_nfp does not fire (and says so, once); every NQ algo stages and fires at its own time on
    its booked paper accounts, places the right OCO stops, and the daily rules (day_take) end the day.

The removed strategies (ym930, nq10am, nq_open_long, nq_open_short) are gone from the defaults and the tester.
What this does NOT prove: real broker acks / fills, and broker-fed bars (the md socket is a fake).
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from homebase import config as desk_config
from homebase import inactive, leveltimer
from homebase.broker.base import FillEvent
from homebase.config import AccountCfg, AppCfg, _defaults
from homebase.engine import Engine
from homebase.leveltimer import LevelTimer
from homebase.timer import SelfTimer
from tests.levels_util import strategy_cfg
from tests.test_atrbars import FIRE_NYAM, FIRE_ORB, FIRE_PM, day_minutes
from tests.test_engine_levels import FLEX, PRO, BalAdapter
from tests.test_leveltimer import Clock, FakeMD, run
from tests.test_timer import FakeMD as GcMD

FRI, MON = dt.date(2026, 10, 2), dt.date(2026, 10, 5)
START, END = 7 * 3600 + 50 * 60, 16 * 3600
STEPS = (0.05, 10, 20, 30, 40, 58.5, 59.0, 59.5)
GC_ANCHOR = 3950.0
LEVELS = ("nq_nyam_flex", "nq_nyam_pro", "nq_orb_pro", "nq_pm_flex")


class Day:
    def __init__(self, tmp_path, monkeypatch, date):
        monkeypatch.setattr(desk_config, "config_path", lambda: tmp_path / "config.json")
        monkeypatch.setattr(leveltimer.symbols, "resolve_contract", lambda s: "NQZ6")
        self.date, self.tmp = date, tmp_path
        self.clock = Clock(date)
        strategies = {n: strategy_cfg(n, enabled=True) for n in ("gc_nfp", *LEVELS)}
        paper = lambda **prop: AccountCfg(keyring_key="k", account_name="P", paper=True, prop=prop)  # noqa: E731
        accounts = {"gc1": AccountCfg(keyring_key="g1", account_name="GC1"),
                    "gc2": AccountCfg(keyring_key="g2", account_name="GC2"),
                    "p1": paper(start_balance=50000, rules=FLEX),
                    "p2": paper(start_balance=50000, rules=PRO)}
        book = {"gc_nfp": [{"account": "gc1", "qty": 4}, {"account": "gc2", "qty": 4}],
                "nq_nyam_flex": [{"account": "p1", "qty": 4}], "nq_orb_pro": [{"account": "p1", "qty": 4}],
                "nq_pm_flex": [{"account": "p1", "qty": 4}], "nq_nyam_pro": [{"account": "p2", "qty": 4}]}
        self.cfg = AppCfg(armed=True, accounts=accounts, strategies=strategies, book=book)
        self.ads = {a: BalAdapter(a, 50000.0 if a.startswith("p") else None) for a in accounts}
        self.eng = Engine(self.cfg, self.ads, now_fn=self.clock, root=tmp_path)
        self.mins = day_minutes(13, until_s=END)
        self.by_min = {m[0]: m for m in self.mins}
        self.nq_md = FakeMD(self.clock, self.mins)
        self.gc_md = GcMD(last_trade=GC_ANCHOR, clock=self.clock)
        self.gc = SelfTimer(self.cfg, self.eng, md_factory=lambda: self.gc_md, now_fn=self.clock)
        self.lt = LevelTimer(self.cfg, self.eng, md_factory=lambda: self.nq_md, now_fn=self.clock)
        self.times = [m * 60 + o for m in range(START // 60, END // 60) for o in STEPS]
        self.i = 0

    def advance(self, h, m=0, s=0.0):
        """Tick both timers (and the engine's clock) through every step up to and including h:m:s ET."""
        target = h * 3600 + m * 60 + s
        while self.i < len(self.times) and self.times[self.i] <= target + 1e-9:
            t = self.times[self.i]
            self.i += 1
            self.clock.s = t
            minute, off = int(t // 60) * 60, round(t % 60, 2)
            row = self.by_min.get(minute)
            if row and off in (10, 20, 30, 40):
                self.nq_md.push(row[{10: 1, 20: 2, 30: 3, 40: 4}[off]])
            elif row and off >= 58.5:
                self.nq_md.push(row[4])
            if off == 0.05 and minute % 600 == 0:
                inactive.sweep(self.cfg, self.eng, self.clock().astimezone(leveltimer.ET))
            run(self.gc.tick())
            run(self.lt.tick())
            if off == 10:
                run(self.eng.clock_tick())

    def events(self, name=None, strategy=None):
        p = self.tmp / "journal.jsonl"
        rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
        return [r for r in rows if (name is None or r["event"] == name)
                and (strategy is None or r.get("strategy") == strategy)]

    def fill(self, name, account, side, px, oid=None, qty=4, sym="NQZ6"):
        st = self.eng._state(name, account)
        run(self.eng.on_fill(FillEvent(account_id=account, symbol=sym, side=side, qty=qty, price=px,
                                       raw={"orderId": oid if oid is not None else "x"})))
        return st

    def stops(self, account, root_orders=None):
        """{side: order} of the account's entry brackets, in the order they went out."""
        return {b.side: b for b in self.ads[account].brackets}


@pytest.fixture
def fri(tmp_path, monkeypatch):
    return Day(tmp_path, monkeypatch, FRI)


@pytest.fixture
def mon(tmp_path, monkeypatch):
    return Day(tmp_path, monkeypatch, MON)


# ---------------------------------------------------------------------------------------------- removed
def test_the_removed_strategies_are_gone_everywhere():
    from homebase import strategies
    gone = {"ym930", "nq10am", "nq_open_long", "nq_open_short"}
    assert not gone & set(_defaults().strategies) and not gone & set(strategies.REGISTRY)
    assert set(_defaults().strategies) == {"nq930", "gc_nfp", "gc_cpi"}        # 2026-10-08: the desk ships these three only
    assert not set(LEVELS) & set(_defaults().strategies) and "gc_nfp" not in _defaults().book
    assert _defaults().strategies["gc_nfp"].enabled is False         # ships off and unbooked
    for n in LEVELS:                                                 # the levels algos stay off and unbooked as references
        assert strategy_cfg(n).enabled is False


# ---------------------------------------------------------------------------------------------- Friday
def test_friday_gc_nfp_fires_at_082959_and_not_before_and_the_nq_algos_run_beside_it(fri):
    fri.advance(8, 29, 58.0)
    assert fri.ads["gc1"].brackets == [] and fri.ads["gc2"].brackets == []
    assert not fri.events("timer_fired")
    fri.advance(8, 29, 59.05)
    fired, = fri.events("timer_fired", "gc_nfp")
    assert fired["late"] is False and fired["anchor_source"] == "pre_open"
    for gc in ("gc1", "gc2"):
        s = fri.stops(gc)
        assert (s["Buy"].order_type, s["Buy"].price, s["Buy"].stop_price, s["Buy"].tp_price, s["Buy"].qty) == \
            ("Stop", 3952.0, 3947.0, 3959.7, 4)
        assert (s["Sell"].price, s["Sell"].stop_price, s["Sell"].tp_price) == (3948.0, 3953.0, 3940.3)
    # the long fills a tick through: the position is live and the sibling stop is cancelled (OCO)
    st = fri.fill("gc_nfp", "gc1", "Buy", 3952.25, oid=fri.eng._state("gc_nfp", "gc1").upper_id, sym="GCZ6")
    assert st.status == "live"
    assert fri.ads["gc1"].cancelled                          # the other leg
    assert not fri.events("inactive_today", "gc_nfp")        # on its day: nothing to say
    fri.advance(16, 0, 0)
    assert len(fri.events("timer_fired", "gc_nfp")) == 1       # it never repeats
    # the NQ algos ran their day on the same desk
    fired = {e["strategy"] for e in fri.events("level_fired")}
    assert fired == set(LEVELS)


# ---------------------------------------------------------------------------------------------- Monday
def test_monday_gc_nfp_is_silent_and_says_so_once(mon):
    mon.advance(10, 0, 0)
    assert mon.ads["gc1"].brackets == [] and mon.ads["gc2"].brackets == []
    assert mon.gc.status()["strategies"] == {}
    said = mon.events("inactive_today", "gc_nfp")
    assert len(said) == 1 and said[0]["code"] == "not_scheduled_today" and "2026-10-02" in said[0]["reason"]
    mon.advance(16, 0, 0)
    assert len(mon.events("inactive_today", "gc_nfp")) == 1


def test_monday_every_nq_algo_stages_fires_on_time_places_the_right_orders_and_the_daily_rule_ends_the_day(mon):
    # ---- 09:30 nyam_flex (p1) + nyam_pro (p2)
    mon.advance(9, 29, 59.0)
    assert mon.ads["p1"].brackets == [] and mon.ads["p2"].brackets == []
    assert {e["strategy"] for e in mon.events("level_staged")} == {"nq_nyam_flex", "nq_nyam_pro"}
    mon.advance(9, 30, 0.05)
    fired = {e["strategy"]: e for e in mon.events("level_fired")}
    assert set(fired) == {"nq_nyam_flex", "nq_nyam_pro"} and all(e["result"] for e in fired.values())
    for name, acct in (("nq_nyam_flex", "p1"), ("nq_nyam_pro", "p2")):
        g = fired[name]["geometry"]
        s = mon.stops(acct)
        assert (s["Buy"].order_type, s["Buy"].price, s["Sell"].price, s["Buy"].qty) == ("Stop", g["upper"], g["lower"], 4)
        assert s["Buy"].stop_price == g["upper"] - g["sl_pts"] and s["Sell"].stop_price == g["lower"] + g["sl_pts"]
        assert g["upper"] > g["lower"] and fired[name]["late"] is False
        assert g["upper"] - g["lower"] == pytest.approx(2 * 0.25 * g["atr"], abs=0.5)
    # ---- nyam_pro: the long fills, then the account's target take closes it -> graded tp
    pro = mon.eng._state("nq_nyam_pro", "p2")
    up = mon.stops("p2")["Buy"].price
    mon.fill("nq_nyam_pro", "p2", "Buy", up, oid=pro.upper_id)
    assert pro.status == "live" and pro.take_src in ("target_take", "day_take") and pro.tp_pts > 0
    mon.fill("nq_nyam_pro", "p2", "Sell", up + pro.tp_pts)
    assert (pro.status, pro.exit_reason) == ("done", "tp")
    # ---- nyam_flex: never fills; its resting entries are cancelled at 10:55
    mon.advance(10, 56, 0)
    flex = mon.eng._state("nq_nyam_flex", "p1")
    assert (flex.status, flex.exit_reason) == ("done", "no_fill")
    # ---- 11:05 orb_pro (p1): the range break stop is placed, fills, and stops out (no lock)
    mon.advance(11, 4, 59.0)
    assert not mon.events("level_fired", "nq_orb_pro")
    mon.advance(11, 5, 0.05)
    orb_ev, = mon.events("level_fired", "nq_orb_pro")
    assert orb_ev["result"] and orb_ev["geometry"]["shape"] == "orb" and orb_ev["late"] is False
    orb = mon.eng._state("nq_orb_pro", "p1")
    s = mon.stops("p1")                                       # p1's brackets so far: flex(2) then orb(2): last two
    orb_buy = mon.ads["p1"].brackets[-2]
    assert orb_buy.side == "Buy" and orb_buy.price == orb_ev["geometry"]["upper"]
    mon.fill("nq_orb_pro", "p1", "Buy", orb_buy.price, oid=orb.upper_id)
    mon.fill("nq_orb_pro", "p1", "Sell", orb_buy.stop_price - 0.25)
    assert orb.exit_reason == "sl" and mon.eng.account_locked("p1") is None
    # ---- 13:30 pm_flex (p1): sized by the account's EOD profit tier, fires on time, take locks the day
    mon.advance(13, 29, 59.0)
    assert not mon.events("level_fired", "nq_pm_flex")
    mon.advance(13, 30, 0.05)
    pm_ev, = mon.events("level_fired", "nq_pm_flex")
    assert pm_ev["result"] and pm_ev["late"] is False
    pm = mon.eng._state("nq_pm_flex", "p1")
    pm_sell = mon.ads["p1"].brackets[-1]
    assert pm_sell.side == "Sell" and pm.qty in (2, 3, 4) and pm.take_src in ("day_take", "target_take")
    mon.fill("nq_pm_flex", "p1", "Sell", pm_sell.price, oid=pm.lower_id, qty=pm.qty)
    mon.fill("nq_pm_flex", "p1", "Buy", pm_sell.price - pm.tp_pts, qty=pm.qty)
    assert (pm.status, pm.exit_reason) == ("done", "tp") and mon.eng.account_locked("p1") == "day_take"
    mon.advance(16, 0, 0)
    assert len(mon.events("level_fired")) == 4
    assert not mon.events("inactive_today", "nq_nyam_flex")      # none of these were silent skips


def test_monday_a_locked_account_makes_the_later_algos_say_why(mon):
    """nyam_flex wins its take on p1 -> day_take locks p1 -> orb_pro and pm_flex (also p1) each say they sat out."""
    mon.advance(9, 30, 0.05)
    flex = mon.eng._state("nq_nyam_flex", "p1")
    buy = [b for b in mon.ads["p1"].brackets if b.side == "Buy"][0]
    mon.fill("nq_nyam_flex", "p1", "Buy", buy.price, oid=flex.upper_id)
    mon.fill("nq_nyam_flex", "p1", "Sell", buy.price + flex.tp_pts)
    assert mon.eng.account_locked("p1") == "day_take"
    mon.advance(13, 31, 0)
    for name in ("nq_orb_pro", "nq_pm_flex"):
        ev, = mon.events("inactive_today", name)
        assert ev["code"] == "every_account_sat_out" and "stopped for the day" in ev["reason"]
        assert mon.events("levels_refused", name)[0]["reason"] == "every_account_sat_out"
    assert len(mon.ads["p1"].brackets) == 2                          # only nyam_flex's pair
