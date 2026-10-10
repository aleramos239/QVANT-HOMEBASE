"""Step B (B4), end to end in one process: a promoted strategy hosted by the REAL Runner in desk mode, its orders
through the REAL LabDesk intake into the REAL Engine, on the REAL paper adapter over the REAL paper book (in process
behind an httpx mock transport, as tests/test_labdesk_paper.py does). The only things stood in for are the two wires:
the runner's POST is a call of LabDesk.event with the body as JSON would carry it, and the Desk's stream is
LabDesk.snapshot handed to the runner by hand. No socket, no service, every store and engine root a tmp_path.

What it proves: the child saw exactly the fills the engine booked, and nothing the tape's model made up."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from homebase import labdesk
from homebase.config import AccountCfg, AppCfg
from homebase.engine import Engine
from homebase.labdesk import LabDesk, Refused
from homebase.labrun import store
from homebase.labrun.deskside import desk_id
from tests.test_broker_paper import Service, adapter, run
from tests.test_engine import Clock
from tests.test_engine_lab import quick
from tests.test_labrun_host import HEAD
from tests.test_labrun_host import Desk as Kit

DAY = dt.date(2026, 9, 14)                   # the engine tests' clock: a Monday
NAME = "pp"
LIMITS = {"max_trades_day": 3, "max_qty": 2, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}

# A buy stop 10 above the last price at 10:00, its stop 5 under the entry, a target at twice the stop, both moved to
# the fill. Every bar it says what it sees.
SOURCE = HEAD + '''class Pp(Strategy):
    id, name, root = "pp", "PP", "NQ"
    bar_minutes = 1
    bar_window = ("10:00", "10:10")

    def times(self):
        return ["10:00:00"]

    def on_session(self, ctx):
        self.o = None

    def on_time(self, ctx, et_time):
        ctx.move_brackets_to_fill = True
        self.o = ctx.stop_entry("long", ctx.last_price + 10, sl=ctx.last_price + 5, tp_rr=2.0)

    def on_bar(self, ctx, bar):
        ctx.plot("flat", ctx.now_ns, 1.0 if ctx.flat else 0.0)
        ctx.plot("status " + self.o.status, ctx.now_ns, 1.0)
        if self.o.fill_px is not None:
            ctx.plot("fill", ctx.now_ns, self.o.fill_px)
            ctx.plot("sl", ctx.now_ns, self.o.fill_sl)
            ctx.plot("tp", ctx.now_ns, self.o.fill_tp)
'''


class InProcess:
    """The runner's line to the Desk with the socket taken out: what DeskClient.send would answer."""

    def __init__(self, ld):
        self.ld, self.bodies, self.said = ld, [], []

    def send(self, body, timeout=5.0):
        self.bodies.append(body)
        try:
            return json.loads(json.dumps(run(self.ld.event(json.loads(json.dumps(body))))))
        except ValueError as e:
            return {"ok": False, "left": True, "status": 400, "detail": str(e)}
        except Refused as e:
            return {"ok": False, "left": True, "status": e.status, "detail": str(e)}

    def say(self, body):
        self.said.append(body)
        self.ld.heartbeat(json.loads(json.dumps(body)))


def last(day, name):
    return day.fills.result.plots[name][-1][1]


def test_a_day_through_the_real_desk_the_child_sees_the_fills_the_engine_booked(tmp_path):
    root = tmp_path / "desklab"
    rec = {"name": NAME, "id": f"draft_{NAME}", "label": "PP", "root": "NQ", "source": SOURCE,
           "sha256": hashlib.sha256(SOURCE.encode()).hexdigest(), "params": {}, "qty": 1, "run": {"id": "r1"}, "notes": [],
           "promoted_utc": "2026-09-10T12:00:00+00:00", "enabled": True, "commission": 4.0, "slippage_ticks": 1.0,
           "session_window": ["09:25", "15:55"], "bar_minutes": 1}    # (a window that ends by the Desk's flat time:
    # this day's match has no window note; a later window books too, with one note)
    store.put(rec, root)

    # ---- the Desk: one paper account, the strategy's limits set and the account booked on the Desk's own page path
    svc = Service()
    (aid,) = [v["id"] for v in svc.books.views()]
    clock = Clock()
    clock.set_et(10, 0)
    cfg = AppCfg(armed=True, accounts={aid: AccountCfg(paper=True, label=aid)}, book={}, strategies={})
    labdesk.attach(cfg, root)
    ad = adapter(svc, aid)
    (tmp_path / "engine").mkdir()
    eng = quick(Engine(cfg, {aid: ad}, now_fn=clock, root=tmp_path / "engine"))
    run(ad.connect())
    run(ad.observe_fills(eng.on_fill))
    ad._task.cancel()                                                        # fills are pulled by hand: no timing
    svc.feed([("09:59:59", 100.0)], aid=aid)
    ld = LabDesk(cfg, eng, {aid: ad}, at=root)
    lab = desk_id(NAME)
    run(ld.refresh())
    run(ld.set_limits(lab, LIMITS))
    run(ld.set_book(lab, [{"account": aid, "qty": 1}]))
    ld.start()

    def prints(rows):
        """The market trades: the book fills what it fills, the engine hears of it, the stream says so."""
        svc.feed(rows, aid=aid)
        run(ad._deliver(run(ad._read())))

    # ---- the runner, with a line to that Desk
    line = InProcess(ld)
    k = Kit(tmp_path, desk=line)
    k.r._nap = lambda s: None
    assert k.at == root

    def stream():
        k.r.take(("desk", "state", json.loads(json.dumps(ld.snapshot()))))

    try:
        k.clock("09:00:00", d=DAY)
        k.open(d=DAY, px=100.0)
        k.rows("09:20:00", [100.0] * 2, d=DAY)
        stream()
        k.r.sync()
        day = k.r.day(NAME)
        assert day.mode == "desk" and day.desk.accounts == [aid] and day.desk.silent() is False

        k.rows("09:59:01", [100.0] * 60, d=DAY)                              # .. 10:00:00: the strategy's entry
        k.clock("10:00:00", d=DAY)
        (body,) = line.bodies
        assert body["strategy"] == lab and body["date"] == DAY.isoformat() and body["seq"] == 2
        assert day.summary()["orders"] == [{"t": "10:00:00", "text": "Buy stop 110.00, stop 105.00, target 2 x the stop",
                                            "refused": None}]
        st = eng.states[f"{lab}@{aid}"]
        book = {o["order_id"]: o for o in run(ad._read())["orders"]}
        assert st.status == "placed" and book[st.upper_id]["stop_price"] == 110.0      # a real order in the book
        assert day.fills.working_entries == 0                                # ... and none in the runner's tape model

        k.rows("10:00:01", [104.0] * 60, d=DAY)                              # the 10:00 bar: working, flat
        stream()
        k.clock("10:01:00", d=DAY)
        assert last(day, "flat") == 1.0 and "status working" in day.fills.result.plots

        prints([("10:01:02", 110.0)])                                        # the stop is touched: the book fills it
        assert (st.status, st.entry_fill) == ("live", 110.25)
        stream()
        k.rows("10:01:01", [110.5] * 60, d=DAY)                              # the runner's tape would fill it too,
        k.clock("10:02:00", d=DAY)                                           # but only the Desk's word is told:
        assert last(day, "fill") == st.entry_fill == 110.25                  # the engine's own fill price,
        assert (last(day, "sl"), last(day, "tp")) == (st.sl_px, st.tp_px) == (105.25, 120.25)    # its moved brackets,
        assert last(day, "flat") == 0.0 and "status filled" in day.fills.result.plots            # and not flat
        assert day.trades() == [] and day.fills.trades() == []

        prints([("10:05:00", 120.5)])                                        # one tick through the target
        assert (st.status, st.exit_reason, st.exit_fill, st.pnl) == ("done", "tp", 120.25, 200.0)
        eng._retry_at.clear()
        run(eng.clock_tick())                                                # its orders read ended: clean
        stream()
        k.rows("10:02:01", [120.5] * 60, d=DAY)
        k.clock("10:03:00", d=DAY)
        assert last(day, "flat") == 1.0                                      # flat again, as the engine booked it
        (trade,) = day.summary()["trades"]
        assert (trade["side"], trade["qty"], trade["entry_px"], trade["exit_px"], trade["reason"], trade["net"]) == \
            ("long", 1, st.entry_fill, st.exit_fill, "tp", st.pnl)
        assert len(line.bodies) == 1 and [b["seq"] for b in line.bodies] == [2]      # one request the whole day

        k.r.beat()                                                           # the Desk's page reads the runner's beat
        view = ld.status_view(lab)
        assert view["mode_today"] == "desk" and view["trades_today"] == 1
        assert k.today(NAME, d=DAY)["mode"] == "desk" and k.today(NAME, d=DAY)["net"] == 200.0
    finally:
        k.r.close()                                                          # a clean stop: the Desk's day is over
        ld.close()
    assert [it["op"] for it in line.bodies[-1]["intents"]] == ["stop"]
    assert ld.snapshot()["strategies"][lab]["stopped"] == "Stopped for today."
    assert k.file(NAME, d=DAY)["state"] == "stopped"
    assert not [p for p in k.spawned if p.poll() is None]
