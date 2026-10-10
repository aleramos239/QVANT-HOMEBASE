"""Step B (B3): a Lab strategy's whole trade through the intake, on the REAL engine and the REAL paper adapter over
the REAL paper book (charts/paperbook.py, in process behind an httpx mock transport: tests/test_broker_paper.py).
Every order, bracket, re-price, cancel and fill below is decided by the book's own fill law. No network, no service."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase import labdesk
from homebase.config import AccountCfg, AppCfg
from homebase.engine import Engine
from homebase.labdesk import LabDesk
from homebase.labrun import store
from homebase.server import create_app
from tests.labdesk_util import DATE, LAB, LIMITS, MARK, Stepper, entry, pair, rec
from tests.test_broker_paper import Service, adapter, run
from tests.test_engine import Clock, FakeAdapter
from tests.test_engine_lab import quick
from tests.trading_util import Mono


class Desk:
    """The engine, the intake and `n` paper accounts on one book service, at 10:00 ET."""

    def __init__(self, tmp_path, n=1, limits=LIMITS):
        self.svc = Service(accounts=n)
        self.ids = [v["id"] for v in self.svc.books.views()]
        self.tmp = tmp_path
        store.put(rec())
        self.clock = Clock()
        self.clock.set_et(10, 0)
        self.cfg = AppCfg(armed=True, accounts={a: AccountCfg(paper=True, label=a) for a in self.ids}, book={}, strategies={})
        labdesk.attach(self.cfg)
        self.ads = {a: adapter(self.svc, a) for a in self.ids}
        self.eng = quick(Engine(self.cfg, self.ads, now_fn=self.clock, root=tmp_path))
        for a, ad in self.ads.items():
            run(ad.connect())
            run(ad.observe_fills(self.eng.on_fill))
            ad._task.cancel()                        # fills are pulled by hand: no timing
            self.svc.feed([("09:59:59", 100.0)], aid=a)
        self.ld = LabDesk(self.cfg, self.eng, self.ads)
        self.ld._mono = Stepper()
        run(self.ld.refresh())
        run(self.ld.set_limits(LAB, limits))
        run(self.ld.set_book(LAB, [{"account": a, "qty": 1} for a in self.ids]))
        self.ld.start()
        self.seq = 0

    def send(self, intents, last=100.0):
        self.seq += 1
        ms = int(self.clock().timestamp() * 1000)
        return run(self.ld.event({"strategy": LAB, "date": DATE, "mark": list(MARK), "seq": self.seq, "t_ns": ms * 10 ** 6,
                                  "state": {"last_price": last, "last_ms": ms, "prices_late": False},
                                  "intents": intents if isinstance(intents, list) else [intents]}))

    def prints(self, rows, aid=None):
        """The market trades: the book fills what it fills, and the engine hears of it."""
        for a in ([aid] if aid else self.ids):
            self.svc.feed(rows, aid=a)
            run(self.ads[a]._deliver(run(self.ads[a]._read())))

    def book(self, aid=None) -> dict:
        return {o["order_id"]: o for o in run(self.ads[aid or self.ids[0]]._read())["orders"]}

    def net(self, aid=None) -> int:
        return run(self.ads[aid or self.ids[0]].get_net_position("NQ"))

    def st(self, aid=None):
        return self.eng.states[f"{LAB}@{aid or self.ids[0]}"]

    def tick(self):
        self.eng._retry_at.clear()
        run(self.eng.clock_tick())

    def journal(self, name):
        p = self.tmp / "journal.jsonl"
        return [r for r in map(json.loads, p.read_text().splitlines()) if r["event"] == name]


def test_a_whole_round_entry_fill_re_priced_brackets_target_and_the_next_round(tmp_path):
    d = Desk(tmp_path)
    out = d.send(entry(1, price=110.0, sl=105.0, tp=None, tp_rr=2.0, move=True))
    assert out["results"][0]["status"] == "working" and out["brain"]["orders"] == {"1": {"status": "working"}}
    st = d.st()
    assert st.status == "placed" and st.upper_id and st.up_sl_id and st.up_tp_id
    assert d.book()[st.up_tp_id]["price"] == 120.0                                 # the provisional target: 110 + 2 x 5

    d.prints([("10:00:02", 110.0)])                                                # the stop is touched: 110 + 1 tick
    assert (st.status, st.entry_side, st.entry_fill, st.entry_qty) == ("live", "Buy", 110.25, 1)
    book = d.book()
    assert book[st.up_sl_id]["stop_price"] == 105.25                               # moved with the fill (fill - ref)
    assert book[st.up_tp_id]["price"] == 120.25                                    # 110.25 + 2 x |110.25 - 105.25|
    snap = d.ld.snapshot()["strategies"][LAB]
    assert snap["brain"]["flat"] is False
    assert snap["brain"]["orders"]["1"] == {"status": "filled", "fill_px": 110.25, "fill_sl": 105.25, "fill_tp": 120.25,
                                            "fill_ms": snap["rounds"][0]["entry_ms"]}
    assert d.send(entry(2))["results"][0]["refused"] == "One position at a time."

    d.prints([("10:05:00", 120.5)])                                                # one tick through the target
    assert (st.status, st.exit_reason, st.exit_fill, st.pnl) == ("done", "tp", 120.25, 200.0)
    assert d.net() == 0
    d.tick()                                                                       # its orders read ended: clean
    snap = d.ld.snapshot()["strategies"][LAB]
    assert snap["brain"]["flat"] is True and snap["rounds"][0]["clean"] is True and d.book() == {}

    out = d.send(entry(3, side="short", price=95.0, sl=99.0, tp=85.0))             # the same day's second trade
    assert out["results"][0]["accounts"][d.ids[0]] == {"ok": True, "round": 2, "reason": None}
    assert out["brain"]["entries_today"] == 2 and d.ld.status_view(LAB)["trades_today"] == 2
    assert [e["round"] for e in d.journal("lab_round")] == [1, 2]


def test_a_stop_with_no_target_rests_alone_and_a_flatten_closes_only_the_round(tmp_path):
    d = Desk(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=None))
    st = d.st()
    assert st.up_sl_id and st.up_tp_id is None and len(d.book()) == 2              # the entry and its stop: no target order
    d.prints([("10:00:02", 110.0)])
    assert st.status == "live" and list(d.book()) == [st.up_sl_id]
    out = d.send({"op": "flatten", "reason": "time"})
    assert out["results"][0]["accounts"][d.ids[0]]["sold"] == 1
    d.prints([("10:01:00", 111.0)])                                                # the market order fills on the next print
    assert (st.status, st.exit_reason) == ("done", "time") and d.net() == 0 and d.book() == {}
    assert st.pnl == round((st.exit_fill - 110.25) * 20, 2)
    assert d.send({"op": "flatten", "reason": "time"})["results"][0]["accounts"] == {d.ids[0]: {"ok": True, "sold": 0, "actions": []}}


def test_a_market_entry_carries_its_stop_into_the_book(tmp_path):
    d = Desk(tmp_path)
    out = d.send(entry(1, kind="market", side="short", sl=104.0, tp=None, tp_rr=1.5, ref=100.0, move=True))
    assert out["results"][0]["status"] == "working"
    d.prints([("10:00:01", 100.0)])
    st = d.st()
    assert (st.status, st.entry_side) == ("live", "Sell") and d.net() == -1
    stop = d.book()[st.dn_sl_id]
    assert stop["stop_price"] == round(104.0 + (st.entry_fill - 100.0), 2)         # the stop moved with the fill
    d.prints([("10:02:00", stop["stop_price"])])                                   # ... and it is a real stop
    assert (st.status, st.exit_reason) == ("done", "sl") and d.net() == 0


def test_a_pair_one_leg_fills_and_the_other_is_gone(tmp_path):
    d = Desk(tmp_path)
    out = d.send(pair(buy=110.0, sell=90.0))
    assert out["brain"]["working"] == 2
    st = d.st()
    d.prints([("10:00:05", 90.0)])
    assert (st.status, st.entry_side, st.entry_fill) == ("live", "Sell", 89.75)
    assert st.upper_id not in d.book()                                             # the buy stop was cancelled
    b = d.ld.snapshot()["strategies"][LAB]["brain"]
    assert b["orders"]["4"]["status"] == "filled" and b["orders"]["3"] == {"status": "cancelled"} and b["working"] == 0


def test_a_cancel_takes_the_resting_entry_and_its_held_legs_out_of_the_book(tmp_path):
    d = Desk(tmp_path)
    d.send(entry(1))
    assert len(d.book()) == 3
    out = d.send({"op": "cancel", "id": 1})
    assert out["results"][0]["accounts"][d.ids[0]]["state"] == "cancelled" and d.book() == {}
    assert (d.st().status, d.st().exit_reason) == ("done", "cancelled") and out["brain"]["flat"] is True


def test_two_accounts_fill_apart_and_the_brain_is_the_first_fill(tmp_path):
    d = Desk(tmp_path, n=2)
    a, b = d.ids
    out = d.send(entry(1, price=110.0, sl=105.0, tp=120.0))
    assert [r["ok"] for r in out["results"][0]["accounts"].values()] == [True, True]
    d.prints([("10:00:02", 110.0)], aid=a)
    snap = d.ld.snapshot()["strategies"][LAB]["brain"]
    assert snap["orders"]["1"]["fill_px"] == 110.25 and snap["flat"] is False      # b still rests its entry
    d.prints([("10:00:03", 110.5)], aid=b)
    assert (d.st(a).entry_fill, d.st(b).entry_fill) == (110.25, 110.75)
    assert d.ld.snapshot()["strategies"][LAB]["brain"]["orders"]["1"]["fill_px"] == 110.25
    out = d.send({"op": "stop", "why": "Strategy error: boom", "flatten": True})
    assert [r["sold"] for r in out["results"][0]["accounts"].values()] == [1, 1]
    d.prints([("10:01:00", 111.0)])
    assert d.net(a) == d.net(b) == 0 and d.book(a) == d.book(b) == {}


def test_a_silent_runner_loses_its_resting_entry_and_a_position_keeps_its_stop(tmp_path):
    d = Desk(tmp_path, n=2)
    a, b = d.ids
    mono = d.ld._mono = Mono()
    d.ld._t0 = mono.t
    d.send(entry(1))
    d.prints([("10:00:02", 110.0)], aid=a)                                         # a is in, b still rests
    mono.t += 21
    run(d.ld._runner_rule())
    assert d.book(b) == {} and d.st(b).exit_reason == "cancelled"
    assert d.net(a) == 1 and set(d.book(a)) == {d.st(a).up_sl_id, d.st(a).up_tp_id}   # its stop and target still work
    assert len(d.journal("lab_runner_down")) == 1


# ---------------------------------------------------------------- through the desk's own routes
@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr("homebase.trading.ChartDesk._views_paused", lambda self: False)
    svc = Service()
    store.put(rec())
    listing = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"accounts": svc.books.listing(), "broken": None})), base_url="http://paper.test")
    cfg = AppCfg(armed=True, accounts={"paper": AccountCfg(paper=True, label="PAPER")}, book={}, strategies={})
    ad = adapter(svc)
    app = create_app(cfg, {"paper": ad}, background=False, adapter_factory=lambda aid, a: FakeAdapter(aid),
                     paper_client=listing, lab=True)
    clock = Clock()
    clock.set_et(10, 0)
    app.state.engine._now = clock
    quick(app.state.engine)
    run(ad.connect())
    run(ad.observe_fills(app.state.engine.on_fill))
    ad._task.cancel()
    svc.feed([("09:59:59", 100.0)])
    asyncio.run(app.state.labdesk.refresh())
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app, c.svc, c.ad, c.clock, c.tmp = app, svc, ad, clock, tmp_path
        c.H = {"X-Homebase-Key": (tmp_path / "lab.key").read_text().strip()}
        yield c
        app.state.labdesk.close()


def test_the_owner_sets_it_up_on_the_page_and_the_runner_trades_it_through_the_door(desk):
    c = desk
    assert c.post("/api/lab-limits", json={"strategy": LAB, "limits": LIMITS}).status_code == 200
    r = c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": "paper", "qty": 1}]})
    assert r.status_code == 200, r.text
    ms = int(c.clock().timestamp() * 1000)
    ev = {"strategy": LAB, "date": DATE, "mark": list(MARK), "seq": 1, "t_ns": ms * 10 ** 6,
          "state": {"last_price": 100.0, "last_ms": ms, "prices_late": False}, "intents": [entry(1, tp=None, tp_rr=2.0)]}
    out = c.post("/api/lab/intent", headers=c.H, json=ev).json()
    assert out["results"][0]["accounts"]["paper"] == {"ok": True, "round": 1, "reason": None}
    st = c.app.state.engine._state(LAB, "paper")
    book = {o["order_id"]: o for o in run(c.ad._read())["orders"]}
    assert set(book) == {st.upper_id, st.up_sl_id, st.up_tp_id} and book[st.up_tp_id]["price"] == 120.0
    c.svc.feed([("10:00:02", 110.0)])
    run(c.ad._deliver(run(c.ad._read())))
    assert st.status == "live" and run(c.ad.get_net_position("NQ")) == 1
    s = c.get("/api/status").json()["strategies"][LAB]
    assert (s["lab"]["state"], s["lab"]["trades_today"], s["day_status"]) == ("in_position", 1, "live")
    assert c.get("/api/lab/state", headers=c.H).json()["strategies"][LAB]["brain"]["orders"]["1"]["status"] == "filled"
    r = c.post("/api/strategy", json={"strategy": LAB, "enabled": False})          # the Desk's switch
    assert r.status_code == 200
    stopped = [e for e in map(json.loads, (c.tmp / "journal.jsonl").read_text().splitlines()) if e["event"] == "lab_stopped"]
    assert [(e["why"], e["flatten"], e["cause"]) for e in stopped] == [("off", False, "desk")]
    assert st.status == "live" and run(c.ad.get_net_position("NQ")) == 1           # the position keeps its stop
    ev2 = {**ev, "seq": 2, "intents": [{"op": "flatten", "reason": "time"}, entry(2)]}
    out = c.post("/api/lab/intent", headers=c.H, json=ev2).json()                  # off: an exit still goes
    assert out["results"][0]["accounts"]["paper"]["sold"] == 1 and out["results"][1]["refused"] == "It is off."
    c.svc.feed([("10:01:00", 111.0)])
    run(c.ad._deliver(run(c.ad._read())))
    assert st.status == "done" and run(c.ad.get_net_position("NQ")) == 0
