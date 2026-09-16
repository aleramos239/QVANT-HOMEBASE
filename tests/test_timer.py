"""Self-fire timer: gate → stage → anchor → fire, and every fail-safe."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.timer import SelfTimer
from tests.test_engine import Clock, FakeAdapter

FIX = json.loads((Path(__file__).parent / "fixture_gate_nq2024.json").read_text())


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeMD:
    def __init__(self, bars=None, last_trade=None):
        self.connected = True
        self.bars = bars if bars is not None else FIX["bars"]
        self.last_trade = last_trade
        self.last_trade_ts = time.time()
        self.subs = []

    async def connect(self): ...
    async def daily_bars(self, symbol, n=60): return self.bars[-n:]
    async def subscribe_quote(self, symbol):
        self.subs.append(symbol); return symbol
    async def unsubscribe_quote(self, sym): self.subs.remove(sym)


def mk(tmp_path, *, last_trade=24500.0, clock=None):
    clock = clock or Clock()
    cfg = AppCfg(armed=False, webhook_secret="s", account=AccountCfg(),
                 strategies={"nq930": StrategyCfg(
                     symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0,
                     tp_pts=15.0, enabled=True, gated=True, self_fire=True)})
    engine = Engine(cfg, FakeAdapter(), now_fn=clock, root=tmp_path)
    md = FakeMD(last_trade=last_trade)
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
    engine._state("nq930").status = "placed"              # e.g. TV won the race
    _drive_to_fire(timer, clock)
    assert timer.status()["strategies"]["nq930"]["stage"] == "done"
    assert any(e["event"] == "timer_deferred" for e in events(tmp_path))


def test_timer_quiet_on_weekend(tmp_path):
    timer, engine, md, clock = mk(tmp_path)
    clock.dt = clock.dt.replace(day=13)                   # Sunday 2026-09-13
    clock.set_et(9, 30); clock.dt = clock.dt.replace(day=13)
    run(timer.tick())
    assert timer.status()["strategies"] == {}
