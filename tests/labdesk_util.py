"""Shared pieces for the Lab intake tests (Step B, task B3): a desk with ONE promoted strategy (pp, NQ), its limits
set and its accounts booked, on the REAL engine over the engine tests' fake adapters. No broker, no network; the store
is the conftest's temp folder (HOMEBASE_DESKLAB_ROOT) and the engine's root is the test's tmp_path."""
from __future__ import annotations

import json
from types import SimpleNamespace

from homebase import labdesk
from homebase.config import AccountCfg, AppCfg
from homebase.engine import Engine
from homebase.labdesk import LabDesk
from homebase.labrun import store
from tests.test_engine import Clock, run
from tests.test_engine_lab import LabAdapter, quick

NAME, LAB = "pp", "lab_pp"
MARK = ["ab", "2026-10-09T12:00:00+00:00"]
DATE = "2026-09-14"                      # the engine tests' clock: a Monday
LIMITS = {"max_trades_day": 3, "max_qty": 2, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}


def rec(name=NAME, promoted=MARK[1], **kw):
    return {"name": name, "id": f"draft_{name}", "label": "PP", "root": "NQ", "source": "class X: pass\n", "sha256": MARK[0],
            "params": {}, "qty": 1, "run": {"id": "r1"}, "notes": [], "promoted_utc": promoted, "enabled": True,
            "commission": 4.0, "slippage_ticks": 1.0, "session_window": ["09:25", "16:00"], "bar_minutes": 5, **kw}


class Stepper:
    """The intake's monotonic clock in these tests: every read is 0.3 s after the last, so the rate limit (five
    entry requests a second) never depends on how fast the machine is. A test of the limit, the hold or the
    heartbeat rule puts its own clock in (tests.trading_util.Mono)."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        self.t += 0.3
        return self.t


def mkdesk(tmp_path, accounts=("a1",), qty=1, armed=True, at=(10, 0), enabled=True, limits=LIMITS, extra=None,
           book=None, start=True, own_store=False):
    """A desk at `at` ET whose Lab strategy is on, has limits and is booked on `accounts` at `qty` (0: not booked).
    `extra`: {name: StrategyCfg} of other strategies, `book`: their rows. own_store: a second desk in one test gets a
    store of its own under its tmp_path (one desk owns a store). -> ld, cfg, eng, ads, clock, tmp."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "store" if own_store else None
    store.put(rec(enabled=enabled), root)
    clock = Clock()
    clock.set_et(*at)
    cfg = AppCfg(armed=armed,
                 accounts={a: AccountCfg(keyring_key="k", account_name=a.upper(), label=a.upper()) for a in accounts},
                 book=dict(book or {}), strategies=dict(extra or {}))
    labdesk.attach(cfg, root)
    ads = {a: LabAdapter(a) for a in accounts}
    eng = quick(Engine(cfg, ads, now_fn=clock, root=tmp_path))
    ld = LabDesk(cfg, eng, ads, at=root)
    ld._mono = Stepper()                 # never "five requests in one second" because a test machine is fast
    run(ld.refresh())                    # it takes the store and reads every sidecar: from here it may write
    if limits:
        run(ld.set_limits(LAB, limits))
    if limits and qty:
        run(ld.set_book(LAB, [{"account": a, "qty": qty} for a in accounts]))
    if start:
        ld.start()
    return SimpleNamespace(ld=ld, cfg=cfg, eng=eng, ads=ads, clock=clock, tmp=tmp_path)


def now_ms(d) -> int:
    return int(d.clock().timestamp() * 1000)


def entry(iid=1, kind="stop", side="long", price=110.0, sl=105.0, tp=120.0, tp_rr=None, ref="price", move=False,
          qty=1, own_qty=False) -> dict:
    """An entry intent as the child writes it. Defaults: a buy stop at 110, stop 105 ($100 at risk on one NQ)."""
    price = None if kind == "market" else price
    return {"op": "entry", "id": iid, "kind": kind, "side": side, "price": price, "qty": qty, "own_qty": own_qty,
            "sl": sl, "tp": tp, "tp_rr": tp_rr, "ref": price if ref == "price" else ref, "move": move}


def pair(buy=110.0, sell=90.0, dist=5.0, tp=10.0) -> list:
    return [entry(3, side="long", price=buy, sl=buy - dist, tp=buy + tp),
            entry(4, side="short", price=sell, sl=sell + dist, tp=sell - tp), {"op": "oco", "ids": [3, 4]}]


def body(d, intents, seq=1, last=100.0, age_ms=0, late=False, **over) -> dict:
    """One event as the runner posts it (design C2)."""
    ms = now_ms(d)
    return {"strategy": LAB, "date": DATE, "mark": list(MARK), "seq": seq, "t_ns": ms * 1_000_000,
            "state": {"last_price": last, "last_ms": ms - age_ms, "prices_late": late},
            "intents": intents if isinstance(intents, list) else [intents], **over}


def send(d, intents, seq=1, **kw) -> dict:
    return run(d.ld.event(body(d, intents, seq, **kw)))


def journal(tmp_path, event=None) -> list:
    p = tmp_path / "journal.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if event is None or r["event"] == event]
