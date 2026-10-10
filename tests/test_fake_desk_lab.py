"""Step B (B5): the practice Desk's Lab mode (tools/fake_desk.py --lab). The REAL engine, the REAL LabDesk and the REAL
runner routes on three simulated accounts (tools/sim_adapter.py); in the first test also the REAL runner in desk mode.
Everything runs in this process: no socket is opened, no service is started, nothing reads port 8850 or 8852, and
every store and engine folder is a tmp_path."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from homebase import desk_api, engine as engine_mod, labdesk as labdesk_mod
from homebase.labrun import host, match, store
from homebase.labrun.deskside import desk_id
from tests.labdesk_util import DATE, LAB, LIMITS, MARK, Stepper, entry, pair, rec
from tests.test_broker_paper import run
from tests.test_engine_lab import quick
from tests.test_labrun_desk_e2e import InProcess
from tests.test_labrun_host import HEAD, ms_of, plain
from tests.test_labrun_host import Desk as Kit
from tools import fake_desk
from tools.fake_desk import LabRig, StreamClock, create_lab_desk, lab_page, refused_folder, ticks_url

DAY = dt.date(2026, 9, 14)                   # a Monday (labdesk_util.DATE)
KEY = "ab" * 32
A1, A2, LIVE = "sim041", "sim047", "live099"
STATIC = Path(fake_desk.__file__).resolve().parents[1] / "homebase" / "static"


def at(hms: str, extra_ms: int = 0) -> int:
    return ms_of(hms, extra_ms, DAY)


class Lab:
    """A practice Desk at `hms` on DAY: one promoted strategy (lab_pp, NQ) with limits, booked on `accounts`, a first
    print at 100. Nothing runs in the background: a test hands it prints and turns the engine's clock by hand."""

    def __init__(self, tmp_path, accounts=(A1,), qty=1, hms="10:00:00", record=None, setup=True, **kw):
        self.tmp, self.store, self.root = tmp_path, tmp_path / "desklab", tmp_path / "engine"
        if record is not False:
            store.put(record or rec(), self.store)
        self.clock = StreamClock()
        self.clock.heard(at(hms))
        self.app = create_lab_desk(self.store, self.root, key=KEY, clock=self.clock, background=False, **kw)
        self.rig: LabRig = self.app.state.rig
        self.eng, self.ld, self.ads = quick(self.rig.engine), self.rig.labdesk, self.rig.adapters
        self.ld._mono = Stepper()
        self.t = at(hms)
        self.seq = 0
        run(self.rig.start())
        run(self.ld.refresh())
        if setup:
            run(self.ld.set_limits(LAB, LIMITS))
            run(self.ld.set_book(LAB, [{"account": a, "qty": qty} for a in accounts]))
            self.prints([100.0])

    def prints(self, prices, step_ms=1000):
        rows = []
        for p in prices:
            self.t += step_ms
            rows.append([self.t, p, 1])
        run(self.rig.take(("ticks", "NQ", rows)))

    def body(self, intents, last=100.0):
        self.seq += 1
        ms = int(self.clock().timestamp() * 1000)
        return {"strategy": LAB, "date": DATE, "mark": list(MARK), "seq": self.seq, "t_ns": ms * 10 ** 6,
                "state": {"last_price": last, "last_ms": ms, "prices_late": False},
                "intents": intents if isinstance(intents, list) else [intents]}

    def send(self, intents, last=100.0):
        return run(self.ld.event(self.body(intents, last)))

    def st(self, aid=A1):
        return self.eng.states[f"{LAB}@{aid}"]

    def tick(self):
        self.eng._retry_at.clear()
        run(self.eng.clock_tick())

    def journal(self, name):
        p = self.root / "journal.jsonl"
        return [r for r in map(json.loads, p.read_text().splitlines()) if r["event"] == name]

    def fault(self, **body):
        return run(self.rig.fault(body))

    def working(self, aid=A1):
        return {o.id: o for o in self.ads[aid].orders.values() if o.status in ("Working", "Suspended")}

    def net(self, aid=A1):
        return run(self.ads[aid].get_net_position("NQ"))


# ---------------------------------------------------------------- a day through the real runner and the practice Desk
SOURCE = HEAD + '''class Pp(Strategy):
    id, name, root = "pp", "PP", "NQ"

    def times(self):
        return ["10:00:00", "10:10:00", "10:15:00"]

    def on_session(self, ctx):
        self.n = 0

    def on_time(self, ctx, et_time):
        self.n += 1
        if self.n == 1:
            ctx.move_brackets_to_fill = True
            ctx.stop_entry("long", ctx.last_price + 10, sl=ctx.last_price + 5, tp_rr=2.0)
        elif self.n == 2 and ctx.flat:
            ctx.move_brackets_to_fill = False
            ctx.market("short", sl=ctx.last_price + 8)
        elif self.n == 3:
            ctx.flatten("time")
'''


def day_record() -> dict:
    return {"name": "pp", "id": "draft_pp", "label": "PP", "root": "NQ", "source": SOURCE,
            "sha256": hashlib.sha256(SOURCE.encode()).hexdigest(), "params": {}, "qty": 1, "run": {"id": "r1"}, "notes": [],
            "promoted_utc": "2026-09-10T12:00:00+00:00", "enabled": True, "commission": 4.0, "slippage_ticks": 1.0,
            "session_window": ["09:25", "15:55"], "bar_minutes": 0}


class Rehearsal:
    """The runner (tests/test_labrun_host.py's kit) with a line to the practice Desk, both fed the SAME prints in
    step: first the Desk's accounts work them and the engine books what filled, then the Desk's snapshot goes to the
    runner (its stream), then the runner gets the prints and its clock -- so at every event the strategy knows what
    the tester's strategy would know."""

    def __init__(self, tmp_path, accounts=(A1, A2)):
        self.lab = Lab(tmp_path, accounts=accounts, hms="09:00:00", record=day_record(), setup=False)
        ld = self.lab.ld
        self.name = desk_id("pp")
        run(ld.set_limits(self.name, LIMITS))
        run(ld.set_book(self.name, [{"account": a, "qty": 1} for a in accounts]))
        self.line = InProcess(ld)
        self.k = Kit(tmp_path, desk=self.line)
        self.k.r._nap = lambda s: None
        assert self.k.at == self.lab.store
        self.rows: list = []

    def stream(self):
        self.k.r.take(("desk", "state", json.loads(json.dumps(self.lab.ld.snapshot()))))

    def step(self, start: str, prices, clock: str, hand_over=True):
        """Prints one a second from `start`, then the clock: the Desk first, then the runner."""
        t0 = at(start)
        rows = [[t0 + i * 1000, p, 1] for i, p in enumerate(prices)]
        self.rows += rows
        run(self.lab.rig.take(("ticks", "NQ", rows)))
        run(self.lab.rig.take(("clock", at(clock))))
        self.lab.tick()
        if hand_over:
            self.stream()
        self.k.r.on_rows("NQ", rows)
        self.k.clock(clock, d=DAY)


def test_a_day_through_the_real_runner_and_the_practice_desk_gives_the_testers_trades(tmp_path):
    r = Rehearsal(tmp_path)
    k, lab = r.k, r.lab
    try:
        k.clock("09:00:00", d=DAY)
        k.open(d=DAY, px=100.0)
        r.step("09:20:00", [100.0] * 2, "09:20:02")
        k.r.sync()
        day = k.r.day("pp")
        assert day.mode == "desk" and day.desk.accounts == [A1, A2]

        r.step("09:59:01", [100.0] * 60, "10:00:00")             # 10:00:00: a buy stop at 110, stop 105, target 2 x
        assert [b["seq"] for b in r.line.bodies] == [2]
        assert lab.st(A1).status == lab.st(A2).status == "placed"
        assert sorted(o.type for o in lab.working(A1).values()) == ["Limit", "Stop", "Stop"]     # real orders, in its book
        assert day.fills.working_entries == 0                    # ... and none in the runner's own tape model

        r.step("10:00:01", [104.0] * 20 + [110.0] + [112.0] * 39, "10:01:00")     # filled 110.25: 105.25 / 120.25
        assert (lab.st(A1).entry_fill, lab.st(A1).sl_px, lab.st(A1).tp_px) == (110.25, 105.25, 120.25)
        r.step("10:01:01", [118.0] * 30 + [120.5] + [121.0] * 29, "10:02:00")      # one tick through the target
        assert (lab.st(A1).status, lab.st(A1).exit_reason, lab.st(A1).exit_fill, lab.st(A1).pnl) == ("done", "tp", 120.25, 200.0)
        r.step("10:02:01", [121.0] * 480, "10:10:00")            # 10:10:00, flat: sell at the market, stop 129
        assert len(r.line.bodies) == 2 and lab.st(A1).status == "placed"
        r.step("10:10:01", [121.0] + [119.0] * 299, "10:15:00")  # 10:15:00: flatten ("time")
        assert (lab.st(A1).status, lab.st(A1).entry_fill) == ("live", 120.75) and lab.net(A1) == lab.net(A2) == -1
        r.step("10:15:01", [119.0] * 60, "10:16:00")
        assert (lab.st(A1).status, lab.st(A1).exit_reason, lab.st(A1).exit_fill) == ("done", "time", 119.25)
        assert lab.net(A1) == lab.net(A2) == 0 and lab.working(A1) == lab.working(A2) == {}
        r.step("10:16:01", [119.0] * 60, "10:17:00")

        desk = day.trades()
        rows = [(int(t) * 10 ** 6, p, n) for t, p, n in r.rows]
        tester = host.run_day(day_record(), rows, DAY, spawn=plain, daily=[])["trades"]
        cut = lambda ts: [(t["side"], t["qty"], t["entry_price"], t["exit_price"], t["exit_reason"]) for t in ts]  # noqa: E731
        assert cut(desk) == cut(tester) == [("long", 1, 110.25, 120.25, "tp"), ("short", 1, 120.75, 119.25, "time")]
        assert match.compare(desk, tester, 0.25) == {"ok": True, "text": "Matched the backtest: 2 of 2 trades."}
        assert [(t["entry_ns"], t["exit_ns"]) for t in desk][0] == (tester[0]["entry_ns"], tester[0]["exit_ns"])
        # the second account traded the same day: every booked account, the same fills
        both = [[(x["status"], x["entry_fill"], x["exit_fill"], x["exit_reason"], x["pnl"]) for x in lab.eng.lab_rounds(r.name)
                 if x["account"] == a] for a in (A1, A2)]
        assert both[0] == both[1] == [("done", 110.25, 120.25, "tp", 200.0), ("done", 120.75, 119.25, "time", 30.0)]
        assert lab.ld.status_view(r.name)["trades_today"] == 2 and LIVE not in {x["account"] for x in lab.eng.lab_rounds(r.name)}
    finally:
        k.r.close()
        lab.ld.close()
    assert not [p for p in k.spawned if p.poll() is None]


def test_a_stream_that_says_nothing_and_the_runner_sends_no_entry(tmp_path):
    """silent_s on the runner's side: with no word from the Desk's stream for 15 s the runner refuses the entry
    itself, in its own words, and nothing is sent."""
    r = Rehearsal(tmp_path, accounts=(A1,))
    k = r.k
    try:
        k.clock("09:00:00", d=DAY)
        k.open(d=DAY, px=100.0)
        r.step("09:20:00", [100.0] * 2, "09:20:02")
        k.r.sync()
        day = k.r.day("pp")
        assert day.mode == "desk"
        k.wall[0] += 16                                          # ... 16 s of the runner's own time with no snapshot
        r.step("09:59:01", [100.0] * 60, "10:00:00", hand_over=False)
        assert r.line.bodies == [] and r.lab.working() == {}
        assert day.summary()["orders"][0]["refused"] == "The Desk is not answering."
    finally:
        k.r.close()
        r.lab.ld.close()


# ---------------------------------------------------------------- each fault, and the real engine's own sentence
def test_a_round_on_the_simulated_account_fill_moved_brackets_target(tmp_path):
    d = Lab(tmp_path)
    out = d.send(entry(1, price=110.0, sl=105.0, tp=None, tp_rr=2.0, move=True))
    assert out["results"][0]["accounts"][A1] == {"ok": True, "round": 1, "reason": None}
    st = d.st()
    book = d.working()
    assert st.status == "placed" and set(book) == {st.upper_id, st.up_sl_id, st.up_tp_id} and book[st.up_tp_id].price == 120.0
    d.prints([110.0])
    assert (st.status, st.entry_fill) == ("live", 110.25)
    assert (d.working()[st.up_sl_id].price, d.working()[st.up_tp_id].price) == (105.25, 120.25)
    d.prints([120.5])
    assert (st.status, st.exit_reason, st.pnl) == ("done", "tp", 200.0) and d.net() == 0 and d.working() == {}
    d.tick()
    assert d.ld.snapshot()["strategies"][LAB]["rounds"][0]["clean"] is True


def test_reject_next_the_brokers_refusal_and_then_words_nobody_knows(tmp_path):
    d = Lab(tmp_path)
    d.fault(reject_next=1)
    got = d.send(entry(1))["results"][0]
    assert got["accounts"][A1] == {"ok": False, "round": 1, "reason": "The broker refused it: OSO rejected (no orderId returned)"}
    assert got["status"] == "cancelled" and d.working() == {}
    d.tick()
    assert d.send(entry(2))["results"][0]["accounts"][A1]["ok"] is True             # a clear refusal: the next one goes
    d2 = Lab(tmp_path / "two")
    d2.fault(reject_next=1, reject_words="Insufficient margin")
    acct = d2.send(entry(1))["results"][0]["accounts"][A1]
    assert (acct["reason"], acct["detail"]) == (engine_mod.LAB_BAD_ORDER, "The broker refused it: Insufficient margin")
    d2.tick()                                                                        # outcome unknown: out for the day
    assert d2.send(entry(2))["results"][0]["refused"] == engine_mod.LAB_CANNOT_CHECK


def test_reject_next_on_one_account_the_other_takes_the_trade(tmp_path):
    d = Lab(tmp_path, accounts=(A1, A2))
    d.fault(account=A2, reject_next=1)
    got = d.send(entry(1))["results"][0]
    assert got["status"] == "working" and got["accounts"][A1]["ok"] is True and got["accounts"][A2]["ok"] is False
    assert d.working(A2) == {} and len(d.working(A1)) == 3


def test_partial_next_the_rest_is_cancelled_and_the_contract_in_keeps_its_stop(tmp_path):
    d = Lab(tmp_path, qty=2)
    d.fault(partial_next=1)
    d.send(entry(1, price=110.0, sl=105.0, tp=120.0))
    d.prints([110.0])
    st = d.st()
    assert (st.status, st.entry_qty, st.qty) == ("live", 1, 2) and d.net() == 1
    out = d.send({"op": "cancel", "id": 1})["results"][0]["accounts"][A1]
    assert (out["ok"], out["state"], out["filled"]) == (True, "part", 1)
    assert run(d.ads[A1].get_order_state(st.upper_id)) == {"status": "Canceled", "filled_qty": 1}
    assert d.working()[st.up_sl_id].qty == 1                                         # the stop outlives its cancelled entry
    d.prints([105.0])
    assert (st.status, st.exit_reason, st.exit_qty) == ("done", "sl", 1) and d.net() == 0


def test_fill_both_the_engines_emergency_and_the_desk_stops_the_strategy(tmp_path):
    d = Lab(tmp_path)
    d.fault(fill_both=True)
    assert d.send(pair(buy=110.0, sell=90.0))["brain"]["working"] == 2
    d.prints([110.0])
    st = d.st()
    assert (st.status, st.exit_reason) == ("error", "both_filled") and len(d.journal("both_filled_emergency")) == 1
    assert d.net() == 0 and d.working() == {}
    run(d.ld._intake_tick())
    assert d.ld.snapshot()["strategies"][LAB]["stopped"] == labdesk_mod.BOTH_FILLED
    assert d.ld.status_view(LAB)["state"] == "check"
    assert d.send(entry(5))["results"][0]["refused"] == labdesk_mod.STOPPED_TODAY


def test_ack_delay_a_fill_that_beats_the_answer_is_kept_and_booked_after_it(tmp_path):
    d = Lab(tmp_path)
    d.fault(ack_delay_ms=40)

    async def go():
        ask = asyncio.ensure_future(d.ld.event(d.body(entry(1, price=110.0, sl=105.0, tp=120.0))))
        for _ in range(200):                                     # until the order is in the account's book
            await asyncio.sleep(0.001)
            if d.working():
                break
        assert d.st().status == "placing"
        await d.rig.take(("ticks", "NQ", [[d.t + 500, 110.0, 1]]))
        assert d.st().status == "placing" and d.ads[A1].pos["NQ"]["net"] == 1      # filled at the broker, the answer still out
        return await ask
    out = asyncio.new_event_loop().run_until_complete(go())
    assert out["results"][0]["accounts"][A1]["ok"] is True
    assert (d.st().status, d.st().entry_fill) == ("live", 110.25) and len(d.journal("entry_fill")) == 1


def test_order_status_unknown_the_last_trade_cannot_be_checked_until_it_reads_again(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=120.0))
    d.prints([110.0, 120.5])
    assert d.st().status == "done"
    d.fault(order_status_unknown=True)
    d.tick()
    assert d.send(entry(2))["results"][0]["refused"] == engine_mod.LAB_CANNOT_CHECK
    assert d.journal("lab_check")[-1]["reason"] == "orders of the last trade are not all ended"
    d.fault(order_status_unknown=None)
    d.eng.__dict__.get("_lab_tries", {}).clear()
    d.tick()
    assert d.send(entry(3, price=130.0, sl=125.0, tp=140.0), last=120.5)["results"][0]["accounts"][A1] == {
        "ok": True, "round": 2, "reason": None}


def test_order_status_unknown_a_cancel_that_cannot_be_read_back_is_check_it(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1))
    d.fault(order_status_unknown=d.st().upper_id)
    out = d.send({"op": "cancel", "id": 1})["results"][0]["accounts"][A1]
    assert (out["ok"], out["state"]) == (False, "working") and d.st().status == "placed"
    assert d.journal("lab_check")[-1]["reason"].endswith("not cancelled or filled (status unknown)")


def test_position_unreadable_the_account_sits_the_trade_out(tmp_path):
    d = Lab(tmp_path)
    d.fault(position_unreadable=True)
    got = d.send(entry(1))["results"][0]
    assert got["accounts"][A1] == {"ok": False, "round": None, "reason": engine_mod.LAB_NO_POSITION_READ}
    assert got["refused"] == "The Desk cannot read this account's position." and d.working() == {}


def test_close_refused_check_it_and_the_stop_keeps_working(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=None))
    d.prints([110.0])
    d.fault(close_refused=True)
    out = d.send({"op": "flatten", "reason": "time"})["results"][0]["accounts"][A1]
    assert (out["ok"], out["sold"]) == (False, 0)
    assert out["actions"][-2:] == ["market Sell 1: order rejected (no orderId returned)",
                                   "check it — the close order was not confirmed; its stop is still working"]
    st = d.st()
    assert st.status == "live" and d.net() == 1 and list(d.working()) == [st.up_sl_id]
    assert d.ld.status_view(LAB)["rounds"][0]["why"] == engine_mod.LAB_CLOSE_UNCONFIRMED
    d.fault(close_refused=False)
    again = d.send({"op": "flatten", "reason": "time"})["results"][0]["accounts"][A1]
    assert again["sold"] == 0 and d.net() == 1                   # one close order per trade, ever


def test_legs_outlive_the_engine_cancels_the_stop_and_target_itself(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1))
    st = d.st()
    out = d.send({"op": "cancel", "id": 1})["results"][0]["accounts"][A1]           # the paper book's rule (A3)
    assert out["state"] == "cancelled" and d.working() == {}
    assert out["actions"][1:] == [f"cancel {st.up_sl_id}: order {st.up_sl_id} is not working on SIM0000041",
                                  f"cancel {st.up_tp_id}: order {st.up_tp_id} is not working on SIM0000041"]
    d2 = Lab(tmp_path / "two")
    d2.fault(legs_outlive=True)
    d2.send(entry(1))
    st = d2.st()
    out = d2.send({"op": "cancel", "id": 1})["results"][0]["accounts"][A1]
    assert out["actions"] == [f"cancel entry {st.upper_id}: ok", f"cancel {st.up_sl_id}: ok", f"cancel {st.up_tp_id}: ok"]
    assert d2.working() == {} and (st.status, st.exit_reason) == ("done", "cancelled")
    d2.tick()
    assert d2.ld.snapshot()["strategies"][LAB]["rounds"][0]["clean"] is True


def test_timer_placing_the_930_orders_go_first_and_then_the_entry_goes(tmp_path):
    d = Lab(tmp_path)

    async def fast(_s):
        await asyncio.sleep(0)
    d.ld._sleep = fast                                           # the hold's poll, without the wait (its clock steps 0.3 s)

    async def go():
        await d.rig.fault({"timer_placing_s": 0.2})
        assert d.ld.held() is True
        held = await d.ld.event(d.body(entry(1)))
        await asyncio.sleep(0.3)
        assert d.ld.held() is False
        return held, await d.ld.event(d.body(entry(2)))
    held, after = asyncio.new_event_loop().run_until_complete(go())
    assert held["results"][0]["refused"] == labdesk_mod.FIRE_FIRST == "The 9:30 orders go first."
    assert after["results"][0]["accounts"][A1]["ok"] is True and fake_desk.TIMER_STATE not in d.eng.states


def test_stream_drop_ends_the_runners_stream_and_a_new_one_starts_with_a_whole_state(tmp_path):
    d = Lab(tmp_path)

    async def go():
        gen = desk_api.lab_stream(d.ld, heartbeat_s=0.05)
        first = await gen.__anext__()
        out = await d.rig.fault({"stream_drop": True})
        ended = False
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            ended = True
        again = desk_api.lab_stream(d.ld, heartbeat_s=0.05)
        second = await again.__anext__()
        await again.aclose()
        return first, out, ended, second
    first, out, ended, second = asyncio.new_event_loop().run_until_complete(go())
    assert first.startswith("event: state") and out["dropped"] == 1 and ended and second.startswith("event: state")


def test_silent_s_holds_the_stream_back_and_lets_it_go_on_in_order():
    sent, naps = [], []

    class Rig:
        t, silent_until = 100.0, 0.0

        def silent(self):
            return self.t < self.silent_until

        async def sleep(self, s):
            naps.append(s)
            self.t += 1.0

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        for chunk in (b"event: state", b"event: heartbeat"):
            await send({"type": "http.response.body", "body": chunk, "more_body": True})

    async def send(message):
        sent.append((message["type"], message.get("body"), rig.t))

    rig = Rig()
    rig.silent_until = 103.0
    wrapped = fake_desk._Silence(inner, rig)
    run(wrapped({"type": "http", "path": "/api/lab/stream"}, None, send))
    assert sent == [("http.response.start", None, 100.0), ("http.response.body", b"event: state", 103.0),
                    ("http.response.body", b"event: heartbeat", 103.0)] and len(naps) == 3
    sent.clear()
    rig.silent_until = 200.0
    run(wrapped({"type": "http", "path": "/api/status"}, None, send))               # only the runner's stream
    assert [s[2] for s in sent] == [103.0] * 3


def test_chart_kill_is_the_engines_own_kill(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=120.0))
    d.prints([110.0])
    out = d.fault(chart_kill=LAB)
    assert out["chart_kill"][A1]["ok"] is True and "market Sell 1: ok" in out["chart_kill"][A1]["actions"]
    assert d.eng.killed_today(LAB) and d.journal("strategy_killed")
    d.prints([111.0])
    assert d.net() == 0 and d.working() == {} and d.st().status == "done"
    assert d.send(entry(2))["results"][0]["refused"] == labdesk_mod.KILLED


def test_a_fault_that_does_not_read_changes_nothing(tmp_path):
    d = Lab(tmp_path)
    for bad in ({"reject_next": 1, "nope": True}, {"account": "main", "reject_next": 1}, {"silent_s": -1},
                {"stream_drop": False}, {"chart_kill": "nq930"}, {"reject_next": 1, "timer_placing_s": "x"}, []):
        with pytest.raises(ValueError):
            d.fault(**bad) if isinstance(bad, dict) else run(d.rig.fault(bad))
    assert all(ad.faults.reject_next == 0 for ad in d.ads.values()) and not d.rig.silent()
    d.fault(silent_s=5)
    assert d.rig.silent() and d.rig.view()["faults"]["silent_s"] > 4


# ---------------------------------------------------------------- a restart on the same folders
def test_resume_the_days_trades_counters_stopped_and_the_accounts_books_come_back(tmp_path):
    d = Lab(tmp_path, accounts=(A1, A2))
    d.send(entry(1, price=110.0, sl=105.0, tp=120.0))
    d.prints([110.0, 120.5])                                     # round 1: a winner on both accounts
    d.tick()
    d.send(entry(2, side="short", price=115.0, sl=119.0, tp=105.0), last=120.5)
    d.prints([115.0])                                            # round 2: live, its stop at the broker
    assert d.st().status == "live" and d.net() == -1
    d.send({"op": "stop", "why": "Stopped for today.", "flatten": False})
    run(d.rig.fault({"account": A2, "reject_next": 3}))
    d.ld.close()                                                 # the Desk goes down

    b = Lab(tmp_path, record=False, setup=False, hms="10:00:10")
    view = b.ld.status_view(LAB)
    assert view["trades_today"] == 2 and view["limits"]["max_trades_day"] == LIMITS["max_trades_day"]
    assert [(x["account"], x["round"], x["status"], x["pnl"]) for x in view["rounds"]] == [
        (A1, 1, "done", 195.0), (A2, 1, "done", 195.0), (A1, 2, "live", None), (A2, 2, "live", None)]
    snap = b.ld.snapshot()["strategies"][LAB]
    assert snap["stopped"] == "Stopped for today." and snap["answered"] == [1, 2, 3]
    assert b.rig.cfg.book[LAB] == [{"account": A1, "qty": 1}, {"account": A2, "qty": 1}]
    assert b.net(A1) == b.net(A2) == -1 and [o.type for o in b.working().values()] == ["Stop", "Limit"]
    assert b.ads[A2].faults.reject_next == 0                     # a fault is not a fact: it does not come back
    b.seq = 3
    assert b.send(entry(4))["results"][0]["refused"] == labdesk_mod.STOPPED_TODAY
    run(b.rig.take(("live",)))                                   # the stream has caught up: fills are told again
    b.t = d.t
    b.prints([119.0])                                            # the stop the account kept all along
    assert (b.st().status, b.st().exit_reason, b.st().exit_fill) == ("done", "sl", 119.25) and b.net() == 0
    assert json.loads((b.root / "day-2026-09-14.json").read_text())[f"{LAB}@{A1}"]["status"] == "done"


def test_resume_what_filled_while_the_desk_was_down_is_found_by_the_real_restarts_reconcile(tmp_path):
    """Fix round 1, I3: the real Desk calls engine.reconcile_account after every connect (server.py). Here too: at
    the start, and -- on a saved book -- again once the stream's backlog is in (only then does the simulated account
    know what a broker knows at connect). The reconcile, not the clock, finds the fill."""
    d = Lab(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=120.0))
    assert d.st().status == "placed"
    d.ld.close()
    b = Lab(tmp_path, record=False, setup=False, hms="10:00:10")
    b.t = d.t
    b.prints([110.0])                                            # the backlog: it filled while nobody listened
    assert b.net() == 1 and b.st().status == "placed" and b.journal("entry_fill") == []
    run(b.rig.take(("live",)))                                   # no clock tick here
    assert b.st().status == "live" and b.st().entry_side == "Buy"
    assert b.journal("fill_recovered_on_reconnect")[0]["account"] == A1 and b.journal("entry_found_by_check") == []


def test_resume_a_trade_that_closed_while_the_desk_was_down_is_ended_by_the_reconcile(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=None))
    d.prints([110.0])
    assert d.st().status == "live"
    d.ld.close()
    b = Lab(tmp_path, record=False, setup=False, hms="10:00:10")
    assert b.journal("exit_recovered_on_reconnect") == []        # at the start the account still holds it
    b.t = d.t
    b.prints([105.0])                                            # stopped out while the Desk was down
    assert b.net() == 0 and b.st().status == "live"
    run(b.rig.take(("live",)))
    assert b.st().status == "done" and b.journal("exit_recovered_on_reconnect")[0]["account"] == A1


def test_every_account_is_reconciled_right_after_it_connects_and_a_failure_is_journaled_not_fatal(tmp_path):
    store.put(rec(), tmp_path / "desklab")
    clock = StreamClock()
    clock.heard(at("10:00:00"))
    app = create_lab_desk(tmp_path / "desklab", tmp_path / "engine", key=KEY, clock=clock, background=False)
    rig = app.state.rig
    seen = []

    async def reconcile(aid):
        ad = rig.adapters[aid]
        seen.append((aid, ad.connected, ad._on_fill is not None))
        if aid == A2:
            raise RuntimeError("boom")
        return {}
    rig.engine.reconcile_account = reconcile
    run(rig.start())
    assert seen == [(A1, True, True), (A2, True, True), (LIVE, True, True)]         # connected and listening first
    events = [json.loads(x) for x in (tmp_path / "engine" / "journal.jsonl").read_text().splitlines()]
    assert [(e["account"], e["error"]) for e in events if e["event"] == "reconcile_error"] == [(A2, "boom")]
    run(rig.take(("live",)))                                     # a fresh book was never away: no second reconcile,
    run(rig.take(("live",)))                                     # and a later `live` (the stream came back) is none either
    assert len(seen) == 3
    rig.labdesk.close()


def test_a_stop_the_market_ran_through_is_refused_by_the_account_and_the_account_is_out_for_the_day(tmp_path):
    """Fix round 1, I5a, on the real engine: the refusal a rehearsal must be able to show."""
    d = Lab(tmp_path)
    d.prints([111.0])                                            # the market ran; the runner's last price (100) is older
    acct = d.send(entry(1))["results"][0]["accounts"][A1]        # a buy stop at 110
    assert (acct["ok"], acct["reason"]) == (False, engine_mod.LAB_BAD_ORDER) and d.working() == {}
    assert acct["detail"] == "The broker refused it: a buy stop must be above the last price (111.0)"
    d.tick()
    assert d.send(entry(2, price=120.0, sl=115.0, tp=130.0), last=111.0)["results"][0]["refused"] == engine_mod.LAB_CANNOT_CHECK
    assert d.ld.status_view(LAB)["state"] == "check"


def test_the_practice_desks_config_can_never_be_saved(tmp_path, monkeypatch):
    """Fix round 1, M3: config.json is the real Desk's. A save of the practice Desk's config raises and writes
    nothing; every other config is saved as before."""
    import homebase.config as config_mod
    from homebase.config import AppCfg
    target = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "config_path", lambda: target)
    d = Lab(tmp_path / "lab")
    with pytest.raises(RuntimeError, match="practice Desk's config is never saved"):
        config_mod.save(d.rig.cfg)
    assert not target.exists() and not target.with_name("config.json.tmp").exists()
    config_mod.save(AppCfg())                                    # another config: untouched behaviour
    assert json.loads(target.read_text())["armed"] is False
    d2 = Lab(tmp_path / "lab2")                                  # the guard is put on once, not stacked
    with pytest.raises(RuntimeError):
        config_mod.save(d2.rig.cfg)
    assert getattr(config_mod.save, "__wrapped__", None) is not None and not hasattr(config_mod.save.__wrapped__, "__wrapped__")


def test_the_accounts_carry_their_live_mark_and_the_chart_client_neither_follows_nor_trusts_the_environment(tmp_path):
    seen = []

    def chart(request):
        seen.append(str(request.url))
        if request.url.path == "/api/status":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8852/api/status"})
        return httpx.Response(200, json={})
    d = Lab(tmp_path, setup=False, ticks="http://127.0.0.1:8853", own_port=8859, chart_transport=httpx.MockTransport(chart))
    assert {a: ad.live for a, ad in d.ads.items()} == {A1: False, A2: False, LIVE: True}
    client = d.app.state.chart
    assert client.follow_redirects is False and client.trust_env is False and str(client.base_url) == "http://127.0.0.1:8853"
    with TestClient(d.app, base_url="http://127.0.0.1:8859") as c:
        r = c.get("/chart/api/status", follow_redirects=False)
        assert r.status_code == 302 and seen == ["http://127.0.0.1:8853/api/status"]      # never followed to 8852
    d.ld.close()


def test_nothing_the_practice_desk_serves_from_static_names_the_real_ports(desk):
    """Fix round 1, M2: every file under homebase/static, as served: a text file with the real Desk's or the real
    chart service's port has it swapped as the page has; everything else is the file on disk, byte for byte."""
    files = [p for p in STATIC.rglob("*") if p.is_file()]
    assert len(files) > 20
    swapped = 0
    for p in files:
        rel = p.relative_to(STATIC).as_posix()
        r = desk.get("/static/" + rel)
        assert r.status_code == 200, rel
        disk = p.read_bytes()
        assert b":8850" not in r.content and b":8852" not in r.content, rel
        if b":8850" in disk or b":8852" in disk:
            swapped += 1
            assert r.content == disk.replace(b":8852", b":8853").replace(b":8850", b":8859"), rel
        else:
            assert r.content == disk, rel
    assert swapped >= 2                                          # charts/app.js and apple/web.js today
    assert desk.get("/static/charts/app.js").headers["content-type"].startswith(("text/javascript", "application/javascript"))
    for bad in ("/static/%2e%2e/config.json", "/static/..%2fconfig.py", "/static/%2e%2e/%2e%2e/tools/fake_desk.py",
                "/static/nope.js", "/static/", "/static/charts"):
        assert desk.get(bad).status_code == 404, bad


def test_resume_a_trade_left_open_overnight_is_carried_as_a_block_and_stays_one(tmp_path):
    d = Lab(tmp_path)
    d.send(entry(1, price=110.0, sl=105.0, tp=None))
    d.prints([110.0])
    assert d.st().status == "live"
    d.ld.close()
    nxt = Lab(tmp_path, record=False, setup=False)
    nxt.clock.heard(at("10:00:00") + 86_400_000)                 # Tuesday, the position still open
    nxt.ld._lab_calls()
    rows = [x for x in nxt.eng.lab_rounds(LAB) if x.get("carried")]
    assert len(rows) == 1 and rows[0]["account"] == A1 and rows[0]["date"] == DATE
    nxt.ld.close()
    again = Lab(tmp_path, record=False, setup=False)
    again.clock.heard(at("10:00:30") + 86_400_000)
    again.ld._lab_calls()
    view = again.ld.status_view(LAB)
    assert [(x["account"], x["carried"], x["date"]) for x in view["rounds"]] == [(A1, True, DATE)]
    with pytest.raises(labdesk_mod.Refused) as e:
        run(again.ld.clear_block(LAB, A1))                       # the account still holds the contract
    assert e.value.status == 409 and again.net() == 1


def test_arm_survives_a_restart_as_it_does_in_the_real_desks_config(tmp_path):
    d = Lab(tmp_path)
    with TestClient(d.app, base_url="http://127.0.0.1:8859") as c:
        assert c.post("/api/arm", json={"armed": False}).json() == {"ok": True, "armed": False}
    d.ld.close()
    b = Lab(tmp_path, record=False, setup=False)
    assert b.rig.cfg.armed is False and Lab(tmp_path / "fresh").rig.cfg.armed is True


# ---------------------------------------------------------------- the page and its routes
@pytest.fixture()
def desk(tmp_path):
    d = Lab(tmp_path, setup=False, ticks="http://127.0.0.1:8853", own_port=8859, chart_transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"path": request.url.path, "origin": request.headers.get("origin")})))
    with TestClient(d.app, base_url="http://127.0.0.1:8859") as c:
        c.d, c.H = d, {"X-Homebase-Key": KEY}
        yield c
    d.ld.close()


def test_the_page_is_the_one_on_disk_with_every_address_pointed_back_at_the_practice_desk(desk):
    r = desk.get("/")
    disk = (STATIC / "index.html").read_text(encoding="utf-8")
    assert r.status_code == 200 and "8852" not in r.text and "8850" not in r.text
    assert fake_desk.PAGE_CHART_SWAP in r.text and disk.count(fake_desk.PAGE_CHART_LINE) == 1
    a, b = disk.splitlines(), r.text.splitlines()
    assert len(a) == len(b)
    changed = [(x, y) for x, y in zip(a, b) if x != y]
    assert changed and all(":8852" in x or ":8850" in x for x, _ in changed)
    assert "http://localhost:8859/" in r.text and ":8853/backtest" in r.text
    assert desk.get("/static/desklab.js").content == (STATIC / "desklab.js").read_bytes()
    assert (STATIC / "index.html").read_text(encoding="utf-8") == disk


def test_a_page_whose_chart_line_changed_is_not_served(tmp_path):
    (tmp_path / "index.html").write_text("<script>const CHART = 'http://127.0.0.1:8852';</script>")
    with pytest.raises(ValueError, match="chart-service line changed"):
        lab_page(tmp_path, 8859, 8853)


def test_the_pages_chart_reads_go_to_the_private_chart_service_and_nothing_else_does(desk):
    r = desk.get("/chart/api/tester/desklab", headers={"Origin": "http://127.0.0.1:8859"})
    assert r.status_code == 200 and r.json() == {"path": "/api/tester/desklab", "origin": None}
    assert desk.get("/chart/api/tester/runs").status_code == 404
    assert desk.post("/chart/api/tester/desklab", json={}).status_code == 405
    assert desk.post("/chart/api/tester/desklab/onoff", json={}).status_code in (404, 405)


def test_the_status_has_the_real_routes_keys_three_accounts_and_the_lab_block(desk):
    s = desk.get("/api/status").json()
    assert set(s) == {"armed", "chart_trading", "et_now", "readiness", "timer", "levels", "feed", "accounts", "notices",
                      "book", "strategies", "journal"}
    assert {a: v["env"] for a, v in s["accounts"].items()} == {A1: "demo", A2: "demo", LIVE: "live"}
    assert all(v["connected"] is True and v["label"].startswith(("SIM", "FAKELIVE")) for v in s["accounts"].values())
    assert s["armed"] is True and s["et_now"].startswith("2026-09-14T10:00:00")
    one = s["strategies"][LAB]
    assert set(one) == {"cfg", "research", "live", "day_status", "killed", "accounts", "lab"}
    assert (one["cfg"]["kind"], one["cfg"]["symbol"], one["day_status"]) == ("lab", "NQ", "idle")
    assert one["lab"]["name"] == "pp" and one["lab"]["limits"] is None and one["lab"]["state"] == "shadow"
    assert s["readiness"]["checks"][-1]["label"] == "Mode" and s["journal"][0]["event"]


def test_the_owner_sets_it_up_on_the_page_and_the_runner_trades_it_through_the_real_door(desk):
    c, d = desk, desk.d
    r = c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 1}]})
    assert (r.status_code, r.json()["detail"]) == (409, "Set the limits first.")
    r = c.post("/api/lab-limits", json={"strategy": LAB, "limits": {**LIMITS, "max_trades_day": 0}})
    assert (r.status_code, r.json()["detail"]) == (400, "Trades a day: a whole number from 1 to 20.")
    assert c.post("/api/lab-limits", json={"strategy": LAB, "limits": LIMITS}).status_code == 200
    r = c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 3}]})
    assert (r.status_code, r.json()["detail"]) == (409, "Size is capped at 2 here.")
    r = c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 1}, {"account": LIVE, "qty": 1}]})
    assert r.status_code == 200 and r.json()["book"][LAB] == [{"account": A1, "qty": 1}, {"account": LIVE, "qty": 1}]
    assert c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": "main", "qty": 1}]}).status_code == 400
    assert c.post("/api/book", json={"strategy": "nq930", "assignments": []}).status_code == 404
    d.prints([100.0])

    ev = d.body(entry(1, tp=None, tp_rr=2.0))
    assert c.post("/api/lab/intent", json=ev).status_code == 401                    # the real gate: its own key,
    assert c.post("/api/lab/intent", json=ev, headers={**c.H, "Origin": "http://127.0.0.1:8859"}).status_code == 403
    assert c.post("/api/lab/intent", json=ev, headers={"X-Homebase-Key": "cd" * 32}).status_code == 401
    out = c.post("/api/lab/intent", json=ev, headers=c.H).json()
    assert out["results"][0]["accounts"] == {A1: {"ok": True, "round": 1, "reason": None},
                                             LIVE: {"ok": True, "round": 1, "reason": None}}
    assert c.get("/api/lab/state", headers=c.H).json()["strategies"][LAB]["brain"]["orders"]["1"]["status"] == "working"
    assert c.post("/api/lab/heartbeat", headers=c.H, json={"pid": 1, "strategies": {LAB: {"state": "running", "mode": "desk"}}}
                  ).json()["strategies"][LAB] == {"enabled": True, "killed": False, "stopped": None}
    d.prints([110.0])
    s = c.get("/api/status").json()["strategies"][LAB]
    assert (s["lab"]["state"], s["lab"]["trades_today"], s["lab"]["mode_today"], s["day_status"]) == ("in_position", 1, "desk", "live")
    assert c.get("/api/status").json()["accounts"][A1]["open_positions"] == [{"symbol": "NQ", "net": 1}]

    r = c.post("/api/lab-remove", json={"strategy": LAB})
    assert (r.status_code, r.json()["detail"]) == (409, "Flatten it first.")
    r = c.post("/api/lab-clear", json={"strategy": LAB, "account": A1})
    assert (r.status_code, r.json()["detail"]) == (409, engine_mod.LAB_NO_BLOCK)
    assert c.post("/api/lab-clear", json=[]).status_code == 400
    r = c.post("/api/strategy-flatten", json={"strategy": LAB})                      # "Flatten & turn off"
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert r.json()["results"][A1][0] == "market Sell 1: ok" and set(r.json()["results"]) == {A1, LIVE}
    d.prints([111.0])
    assert d.net(A1) == d.net(LIVE) == 0 and d.st().exit_reason == "manual_flat"
    assert [e["cause"] for e in d.journal("lab_stopped")] == ["desk"] and d.journal("manual_flatten")
    assert c.get("/api/status").json()["strategies"][LAB]["cfg"]["enabled"] is False
    d.tick()
    assert c.post("/api/strategy", json={"strategy": LAB, "enabled": True}).json() == {"ok": True, "strategy": LAB, "enabled": True}
    out = c.post("/api/lab/intent", json=d.body(entry(2), last=111.0), headers=c.H).json()
    assert out["results"][0]["refused"] == labdesk_mod.STOPPED_TODAY                # a stopped day is final
    assert c.post("/api/strategy", json={"strategy": "nq930", "enabled": True}).status_code == 404


def test_disarmed_it_is_written_down_only_and_the_kill_disarms_and_closes(desk):
    c, d = desk, desk.d
    c.post("/api/lab-limits", json={"strategy": LAB, "limits": LIMITS})
    c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 1}]})
    d.prints([100.0])
    assert c.post("/api/arm", json={"armed": False}).json() == {"ok": True, "armed": False}
    out = c.post("/api/lab/intent", json=d.body(entry(1)), headers=c.H).json()
    assert out["results"][0]["refused"] == engine_mod.LAB_DISARMED and d.working() == {} and d.journal("dry_run")
    assert c.get("/api/status").json()["strategies"][LAB]["lab"]["state"] == "disarmed"
    c.post("/api/arm", json={"armed": True})
    out = c.post("/api/lab/intent", json=d.body(entry(2)), headers=c.H).json()
    assert out["results"][0]["accounts"][A1]["ok"] is True
    d.prints([110.0])
    r = c.post("/api/kill", json={}).json()
    assert r["armed"] is False and r["results"][A1] == {"cancel_all": {"ok": True, "error": None},
                                                        "flatten_all": {"ok": True, "error": None}}
    assert d.journal("kill_switch") and d.rig.cfg.armed is False
    d.prints([111.0])
    assert d.net() == 0 and d.working() == {}


def test_the_write_guard_and_the_fault_route_are_the_real_gates(desk):
    c = desk
    assert c.post("/api/arm", json={"armed": False}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/arm", content="armed=0", headers={"Content-Type": "text/plain"}).status_code == 415
    assert c.get("/api/status", headers={"Host": "evil.example"}).status_code == 403
    assert c.get("/api/status").json()["armed"] is True
    assert c.post("/fake/lab", json={"reject_next": 1}).status_code == 401
    assert c.get("/fake/lab").status_code == 401
    assert c.post("/fake/lab", json={"reject_next": 1}, headers={**c.H, "Origin": "http://127.0.0.1:8859"}).status_code == 403
    assert c.post("/fake/lab", json={"reject_next": 1}, headers={**c.H, "Host": "desk.example"}).status_code == 403
    r = c.post("/fake/lab", json={"nope": 1}, headers=c.H)
    assert (r.status_code, r.json()["detail"]) == (400, "unknown fault 'nope'")
    r = c.post("/fake/lab", json={"account": A2, "reject_next": 2, "silent_s": 3}, headers=c.H).json()
    assert r["faults"][A2]["reject_next"] == 2 and r["faults"][A1]["reject_next"] == 0 and r["faults"]["silent_s"] > 2
    view = c.get("/fake/lab", headers=c.H).json()
    assert [a["account"] for a in view["accounts"]] == [A1, A2, LIVE] and view["store"] == str(c.d.store)


def test_what_else_the_page_reads_is_answered_in_the_real_shape(desk):
    c = desk
    live = c.get("/api/strategy-live", params={"strategy": LAB})
    assert live.status_code == 200 and isinstance(live.json(), dict)
    assert c.get("/api/strategy-live", params={"strategy": "nq930"}).status_code == 404
    assert c.get("/api/research-equity", params={"strategy": LAB}).json() == {"points": None}
    assert c.get("/api/logins").json() == {"logins": []}
    assert c.get("/api/calendar", params={"month": "2026-09"}).json() == {
        "account": "", "month": "2026-09", "days": {}, "total": 0.0, "history_since": None}


def test_the_background_loops_work_the_prints_the_clock_and_the_settle_by_themselves(tmp_path):
    """What `python -m tools.fake_desk --lab` runs: the pump (the tick client's queue), the engine's clock, the
    sibling watch and LabDesk's own loop -- here inside the test client, with the queue filled by hand."""
    import queue
    import time
    inbox: queue.Queue = queue.Queue()
    store.put(rec(), tmp_path / "desklab")
    clock = StreamClock()
    clock.heard(at("10:00:00"))
    app = create_lab_desk(tmp_path / "desklab", tmp_path / "engine", key=KEY, clock=clock, inbox=inbox)
    H = {"X-Homebase-Key": KEY}

    def until(fn, what, wait_s=8.0):
        end = time.monotonic() + wait_s
        while time.monotonic() < end:
            got = fn()
            if got:
                return got
            time.sleep(0.05)
        pytest.fail(f"never: {what}")

    with TestClient(app, base_url="http://127.0.0.1:8859") as c:
        until(lambda: c.post("/api/lab-limits", json={"strategy": LAB, "limits": LIMITS}).status_code == 200, "the limits")
        assert c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 1}]}).status_code == 200
        t = at("10:00:01")
        inbox.put(("clock", t))
        inbox.put(("ticks", "NQ", [[t, 100.0, 1]]))
        until(lambda: c.get("/fake/lab", headers=H).json()["et_now"].endswith("10:00:01-04:00"), "the clock")
        ev = {"strategy": LAB, "date": DATE, "mark": list(MARK), "seq": 1, "t_ns": t * 10 ** 6,
              "state": {"last_price": 100.0, "last_ms": t, "prices_late": False},
              "intents": [entry(1, price=110.0, sl=105.0, tp=120.0)]}
        assert c.post("/api/lab/intent", json=ev, headers=H).json()["results"][0]["accounts"][A1]["ok"] is True
        inbox.put(("ticks", "NQ", [[t + 1000, 110.0, 1]]))
        until(lambda: c.get("/api/status").json()["strategies"][LAB]["lab"]["state"] == "in_position", "the fill")
        inbox.put(("ticks", "NQ", [[t + 2000, 120.5, 1]]))
        row = until(lambda: [x for x in c.get("/api/lab/state", headers=H).json()["strategies"][LAB]["rounds"]
                             if x["status"] == "done" and x["clean"]], "the trade over and its orders read ended")
        assert (row[0]["exit_reason"], row[0]["pnl"]) == ("tp", 195.0)
        assert c.get("/api/status").json()["accounts"][A1]["realized_pnl"] == 195.0
    app.state.labdesk.close()


# ---------------------------------------------------------------- the copied route bodies follow the real server
SERVER = (Path(fake_desk.__file__).resolve().parents[1] / "homebase" / "server.py").read_text(encoding="utf-8")
TOOL = Path(fake_desk.__file__).read_text(encoding="utf-8")
CALL = __import__("re").compile(r"\b(labdesk|labdesk_mod|engine)\.([A-Za-z_]+)")


def body_of(text: str, head: str) -> str:
    """One function of a module's text: from its `def` line to the next decorator or def at that depth or above."""
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.strip().startswith(head))
    depth = len(lines[i]) - len(lines[i].lstrip())
    out = [lines[i]]
    for line in lines[i + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= depth and not line.strip().startswith(('"""', "#", ")")):
            break
        out.append(line)
    return "\n".join(out)


def calls(text: str) -> set:
    return {f"{a}.{b}" for a, b in CALL.findall(text)}


# what the real route calls that the practice Desk leaves out, and why
NOT_HERE = {
    "async def status(": {"labdesk.on"},                # the practice Desk's Lab side is always on
    "async def arm(": set(),
    "async def kill(": {"engine.kill_strategy"},        # named in a comment of the real body, not called there
    "async def strategy_toggle(": set(),
    "async def strategy_flatten(": set(),
    "async def set_book(": set(),
    "async def lab_limits(": set(),
    "async def lab_remove(": set(),
    "async def lab_clear(": set(),
}
HERE = {"async def status(": "async def status(self)", "async def lab_limits(": "def lab_route(",
        "async def lab_remove(": "def lab_route(", "async def lab_clear(": "def lab_route("}


@pytest.mark.parametrize("head", sorted(NOT_HERE))
def test_every_labdesk_and_engine_call_of_the_real_route_is_made_by_the_practice_desks_route(head):
    """The page routes are copies (server.py cannot be imported: it builds the real app). This holds each copy to the
    real route: every LabDesk / labdesk / engine call the real body makes, the copy makes too. When the real route
    gains a call, this fails until tools/fake_desk.py follows."""
    real = calls(body_of(SERVER, head))
    mine = calls(body_of(TOOL, HERE.get(head, head)))
    if head.startswith("async def lab_"):                        # the three share one handler; their LabDesk call is
        mine |= calls(TOOL[TOOL.index("    lab_route(\"/api/lab-limits\""):TOOL.index("    @app.get(\"/fake/lab\")")])   # at its use
    assert real, head
    assert real - mine - NOT_HERE[head] == set(), (head, sorted(real - mine))


# ---------------------------------------------------------------- what it refuses to start on
MAIN = fake_desk.main_checkout()


def git(cwd, *args):
    import subprocess
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


@pytest.fixture()
def layout(tmp_path, monkeypatch):
    """A made-up machine in tmp_path: a home with a `.homebase/desklab`, and a real git repository (the "main
    checkout") with one worktree under `.worktrees/` and one under `.claude/worktrees/`. HOME points at the made-up
    home, so a refusal that fails here can only ever write inside tmp_path."""
    home, repo = tmp_path / "home", tmp_path / "repo"
    (home / ".homebase" / "desklab").mkdir(parents=True)
    (repo / "homebase" / ".state").mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "commit", "-q", "--allow-empty", "-m", "x")
    git(repo, "worktree", "add", "-q", str(repo / ".worktrees" / "x"), "-b", "x")
    git(repo, "worktree", "add", "-q", str(repo / ".claude" / "worktrees" / "y"), "-b", "y")
    monkeypatch.setenv("HOME", str(home))
    fake_desk.main_checkout.cache_clear()
    yield home.resolve(), repo.resolve()
    getattr(fake_desk.main_checkout, "cache_clear", lambda: None)()


def test_the_main_checkout_is_what_git_says_from_any_worktree_layout(layout):
    """Fix round 1, I2: asked of git (the common dir), not guessed from where the tool's file sits."""
    _, repo = layout
    assert fake_desk.main_checkout(repo) == repo
    assert fake_desk.main_checkout(repo / ".worktrees" / "x") == repo                # the layout a guess gets wrong
    assert fake_desk.main_checkout(repo / ".claude" / "worktrees" / "y") == repo
    (repo / ".worktrees" / "x" / "tools").mkdir()
    assert fake_desk.main_checkout(repo / ".worktrees" / "x" / "tools") == repo
    fake_desk.main_checkout.cache_clear()
    assert MAIN == fake_desk.main_checkout() and (MAIN / ".git").is_dir()            # ... and of this very checkout
    assert Path(fake_desk.__file__).resolve().is_relative_to(MAIN)


def test_when_git_cannot_say_where_the_main_checkout_is_nothing_starts(tmp_path, monkeypatch, capsys):
    fake_desk.main_checkout.cache_clear()
    with pytest.raises(ValueError, match="git could not say"):
        fake_desk.main_checkout(tmp_path)                        # not a repository

    def no_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(fake_desk.subprocess, "run", no_git)
    fake_desk.main_checkout.cache_clear()
    with pytest.raises(ValueError, match="git could not say"):
        fake_desk.main_checkout()
    with pytest.raises(ValueError):
        refused_folder(tmp_path / "store")                       # no answer is a refusal, never "allowed"
    monkeypatch.setattr(fake_desk, "first_clock", lambda *a: pytest.fail("it went on"))
    monkeypatch.setattr(fake_desk, "bind_port", lambda *a: pytest.fail("it went on"))
    with pytest.raises(SystemExit) as e:
        fake_desk.main(["--lab", "--ticks", "http://127.0.0.1:8853", "--store", str(tmp_path / "s")])
    assert e.value.code == 2 and "git could not say" in capsys.readouterr().err
    fake_desk.main_checkout.cache_clear()


REFUSED = [                                  # (which root, the path under it) -- every one must be refused
    ("home", ".homebase"), ("home", ".homebase/desklab"), ("home", ".homebase/desklab/x/y"),
    ("home", ".HOMEBASE/desklab"), ("home", ".Homebase/DeskLab/x"),                 # I1: another spelling, the same folder
    ("repo", ""), ("repo", "homebase/.state"), ("repo", "tmp/store"), ("repo", "HOMEBASE/.STATE"),
    ("repo", ".claude"), ("repo", ".claude/settings"), ("repo", ".claude/worktrees"), ("repo", ".worktrees"),
    ("repo", ".claude/worktreesX/y"), ("repo", ".git/x"),
]
ALLOWED = [("repo", ".worktrees/x/scratch"), ("repo", ".claude/worktrees/y/scratch"), ("repo", ".claude/worktrees/new/s"),
           ("repo", ".WORKTREES/x/scratch"), ("tmp", "store"), ("tmp", "a/b/c")]


@pytest.mark.parametrize("root,rel", REFUSED)
def test_a_folder_of_the_real_desk_or_of_the_main_checkout_is_refused_however_it_is_spelled(root, rel, layout, tmp_path,
                                                                                              monkeypatch):
    home, repo = layout
    monkeypatch.setattr(fake_desk, "main_checkout", lambda start=None: repo)        # what LabRig's own check asks
    folder = {"home": home, "repo": repo}[root] / rel
    assert refused_folder(folder, main=repo, home=home) is not None
    upper = Path(str({"home": home, "repo": repo}[root]).upper()) / rel             # the whole path in capitals
    assert refused_folder(upper, main=repo, home=home) is not None
    for a, b in ((folder, tmp_path / "engine"), (tmp_path / "store", folder)):      # ... and LabRig asks again itself
        with pytest.raises(ValueError):
            LabRig(a, b)
    assert not (tmp_path / "engine").exists() and not (tmp_path / "store").exists()
    assert sorted(p.name for p in (home / ".homebase").iterdir()) == ["desklab"] and list((home / ".homebase" / "desklab").iterdir()) == []


@pytest.mark.parametrize("root,rel", ALLOWED)
def test_a_temp_folder_and_a_worktrees_own_folder_are_allowed(root, rel, layout, tmp_path):
    home, repo = layout
    if rel.startswith(".WORKTREES") and not (repo / ".WORKTREES").exists():
        pytest.skip("a case-sensitive disk: .WORKTREES is another folder there, and refused")
    assert refused_folder({"repo": repo, "tmp": tmp_path}[root] / rel, main=repo, home=home) is None


def test_a_link_into_a_forbidden_place_is_refused_and_so_is_a_link_to_a_place_that_holds_one(layout, tmp_path):
    home, repo = layout
    for name, target in (("to_home", home), ("to_store", home / ".homebase" / "desklab"), ("to_repo", repo),
                         ("to_state", repo / "homebase" / ".state")):
        link = tmp_path / name
        link.symlink_to(target)
        for rel in ("", ".homebase/desklab", "homebase", "new/folder"):
            p = link / rel
            want = target.joinpath(rel)
            inside = any(str(want).startswith(str(x)) for x in (home / ".homebase", repo))
            assert (refused_folder(p, main=repo, home=home) is not None) == inside, (name, rel)
    chain = tmp_path / "chain"
    chain.symlink_to(tmp_path / "to_store")                      # a link to a link
    assert refused_folder(chain / "x", main=repo, home=home) is not None
    ok = tmp_path / "to_tree"
    ok.symlink_to(repo / ".worktrees" / "x")
    assert refused_folder(ok / "scratch", main=repo, home=home) is None


def test_a_forbidden_folder_that_does_not_exist_yet_is_refused_without_regard_to_case(tmp_path):
    """Where nothing exists there is no identity to compare: the spelling decides, and it decides without case (on a
    disk that ignores case the two spellings WILL be one folder once it is made)."""
    home, main = tmp_path / "nohome", tmp_path / "norepo"        # neither exists
    assert refused_folder(home / ".homebase" / "desklab", main=main, home=home) is not None
    assert refused_folder(home / ".HOMEBASE" / "desklab", main=main, home=home) is not None
    assert refused_folder(tmp_path / "NoHome" / ".HomeBase", main=main, home=home) is not None
    assert refused_folder(tmp_path / "NOREPO" / "homebase" / ".state", main=main, home=home) is not None
    assert refused_folder(tmp_path / "norepo" / ".claude" / "worktrees" / "t" / "s", main=main, home=home) is None
    assert refused_folder(tmp_path / "norepo" / ".CLAUDE" / "worktrees" / "t" / "s", main=main, home=home) is not None   # exact
    assert refused_folder(tmp_path / "elsewhere", main=main, home=home) is None


def test_the_real_folders_of_this_machine_are_refused_too():
    """The same rule on the real paths (a pure question: nothing is opened or made)."""
    home = Path.home()
    for p in (home / ".homebase" / "desklab", "~/.homebase/desklab", "~/.HOMEBASE/desklab", home / ".homebase",
              MAIN, MAIN / "homebase" / ".state", Path(str(MAIN).upper()) / "homebase", MAIN / ".claude" / "settings.json"):
        assert refused_folder(p) is not None, p
    assert refused_folder(MAIN / ".claude" / "worktrees" / "some-tree" / "scratch") is None


@pytest.mark.parametrize("url", ["http://127.0.0.1:8850", "http://127.0.0.1:8852", "http://localhost:8852/",
                                 "http://127.0.0.1:8859", "http://10.0.0.5:8853", "https://127.0.0.1:8853",
                                 "http://127.0.0.1", "http://127.0.0.1:8853/api", "127.0.0.1:8853"])
def test_ticks_must_be_this_machine_and_never_the_real_desk_the_real_chart_service_or_itself(url):
    with pytest.raises(ValueError):
        ticks_url(url, 8859)


def test_ticks_takes_a_private_chart_service():
    assert ticks_url("http://127.0.0.1:8853", 8859) == "http://127.0.0.1:8853"
    assert ticks_url("http://localhost:8854/", 8859) == "http://localhost:8854"


@pytest.mark.parametrize("argv", [
    ["--lab", "--port", "8850", "--ticks", "http://127.0.0.1:8853", "--store", "TMP"],
    ["--lab", "--port", "8852", "--ticks", "http://127.0.0.1:8853", "--store", "TMP"],
    ["--lab", "--port", "8853", "--ticks", "http://127.0.0.1:8855", "--store", "TMP"],
    ["--lab", "--ticks", "http://127.0.0.1:8852", "--store", "TMP"],
    ["--lab", "--ticks", "http://127.0.0.1:8850", "--store", "TMP"],
    ["--lab", "--ticks", "http://127.0.0.1:8859", "--store", "TMP"],
    ["--lab", "--ticks", "http://127.0.0.1:8853", "--store", str(Path.home() / ".homebase" / "desklab")],
    ["--lab", "--ticks", "http://127.0.0.1:8853", "--store", str(MAIN / "store")],
    ["--lab", "--ticks", "http://127.0.0.1:8853", "--store", "TMP", "--resume", str(MAIN / "homebase" / ".state")],
    ["--lab", "--ticks", "http://127.0.0.1:8853", "--store", "TMP", "--resume", "TMP/not-there"],
    ["--lab", "--ticks", "http://127.0.0.1:8853"],
    ["--lab", "--store", "TMP"],
    ["--store", "TMP"],
    ["--ticks", "http://127.0.0.1:8853"],
])
def test_the_tool_does_not_start_on_a_forbidden_port_address_or_folder(argv, tmp_path, monkeypatch, capsys):
    def never(*a, **k):
        raise AssertionError("it went on to open a connection")
    monkeypatch.setattr(fake_desk, "first_clock", never)
    monkeypatch.setattr(fake_desk.uvicorn, "run", never)
    monkeypatch.setattr(fake_desk, "write_key", never)
    monkeypatch.setattr(fake_desk, "bind_port", never)
    monkeypatch.setattr(fake_desk, "serve_lab", never)
    with pytest.raises(SystemExit) as e:
        fake_desk.main([a.replace("TMP", str(tmp_path)) for a in argv])
    assert e.value.code == 2 and "error:" in capsys.readouterr().err


class Sock:
    """What bind_port hands back, in a test: never a socket."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_with_no_clock_from_the_tick_stream_it_does_not_start(tmp_path, monkeypatch, capsys):
    sock = Sock()
    monkeypatch.setattr(fake_desk, "bind_port", lambda port: sock)
    monkeypatch.setattr(fake_desk, "first_clock", lambda ticks: None)
    monkeypatch.setattr(fake_desk, "serve_lab", lambda *a, **k: pytest.fail("it served"))
    monkeypatch.setattr(fake_desk, "write_key", lambda p: pytest.fail("it wrote a key"))
    assert fake_desk.main(["--lab", "--ticks", "http://127.0.0.1:8853", "--store", str(tmp_path / "s")]) == 1
    assert "did not start" in capsys.readouterr().err and not (tmp_path / "s").exists()
    assert sock.closed is True                                   # the port is given back


def test_a_port_that_is_taken_stops_the_start_before_the_key_file_is_touched(tmp_path, monkeypatch, capsys):
    """Fix round 1, M1: a second start beside a running practice Desk must not write a new key over the one the
    running Desk holds (the runner reads the file at every request)."""
    asked = []
    monkeypatch.setattr(fake_desk, "bind_port", lambda port: asked.append(port))    # None: taken
    monkeypatch.setattr(fake_desk, "first_clock", lambda ticks: pytest.fail("it went on to the tick stream"))
    monkeypatch.setattr(fake_desk, "write_key", lambda p: pytest.fail("it wrote a key"))
    monkeypatch.setattr(fake_desk, "serve_lab", lambda *a, **k: pytest.fail("it served"))
    assert fake_desk.main(["--lab", "--ticks", "http://127.0.0.1:8853", "--store", str(tmp_path / "s"), "--port", "8861"]) == 1
    assert asked == [8861] and "Port 8861 is taken" in capsys.readouterr().err and not (tmp_path / "s").exists()


def test_lab_mode_starts_on_the_replayed_day_with_a_fresh_key_and_a_fresh_engine_folder(tmp_path, monkeypatch, capsys):
    served, keys, order, sock = [], [], [], Sock()

    def serve(app, s):
        order.append("serve")
        served.append((app, s))

    def key(path):
        order.append("key")
        keys.append(path)
        return KEY

    def bind(port):
        order.append(("bind", port))
        return sock
    monkeypatch.setattr(fake_desk, "first_clock", lambda ticks: order.append("clock") or at("09:20:00"))
    monkeypatch.setattr(fake_desk, "bind_port", bind)
    monkeypatch.setattr(fake_desk, "serve_lab", serve)
    monkeypatch.setattr(fake_desk.uvicorn, "run", lambda *a, **k: pytest.fail("it bound a port by itself"))
    monkeypatch.setattr(fake_desk, "write_key", key)
    monkeypatch.setattr("homebase.labrun.tickclient.TickClient.run", lambda self, stop: None)     # no connection
    monkeypatch.setattr("tempfile.mkdtemp", lambda prefix: str(tmp_path / (prefix + "x")))
    monkeypatch.setattr(desk_api, "ensure_key", lambda path: pytest.fail(f"it opened a real Desk's key file: {path}"))
    (tmp_path / "fake-lab-desk-x").mkdir()
    store.put(rec(), tmp_path / "s")
    state = fake_desk.state_dir()
    real = {n: (state / n).stat().st_mtime_ns if (state / n).exists() else None
            for n in (desk_api.KEY_FILE, desk_api.LAB_KEY_FILE)}
    assert fake_desk.main(["--lab", "--ticks", "http://127.0.0.1:8853", "--store", str(tmp_path / "s")]) == 0
    (app, got), = served
    assert got is sock and order == [("bind", 8859), "clock", "key", "serve"]     # the port is held before the key is written
    assert [(k.name, k.parent) for k in keys] == [("fake-lab.key", state)]         # ONE key file, its own
    assert real == {n: (state / n).stat().st_mtime_ns if (state / n).exists() else None for n in real}
    rig = app.state.rig
    assert rig.root == tmp_path / "fake-lab-desk-x" and rig.roots() == ["NQ"]
    # the engine is on the REPLAYED day and its New York time, whatever the wall clock says
    assert rig.engine._today() == "2026-09-14" and rig.engine.now_et().strftime("%H:%M:%S") == "09:20:00"
    said = capsys.readouterr().err
    assert app.state.lab_key == KEY and "--resume" in said
    assert f"--desk http://127.0.0.1:8859 --desk-key {state / 'fake-lab.key'}" in said.splitlines()[-1]   # one line
    rig.labdesk.close()


def test_the_practice_desk_only_ever_names_its_own_key_file(monkeypatch):
    assert fake_desk.lab_key_path() == fake_desk.state_dir() / "fake-lab.key"
    assert fake_desk.LAB_KEY_FILE not in (desk_api.KEY_FILE, desk_api.LAB_KEY_FILE, fake_desk.KEY_FILE)
    for name in (desk_api.KEY_FILE, desk_api.LAB_KEY_FILE):
        monkeypatch.setattr(fake_desk, "LAB_KEY_FILE", name)
        with pytest.raises(ValueError, match="real Desk's key file"):
            fake_desk.lab_key_path()
    sim = (Path(fake_desk.__file__).parent / "sim_adapter.py").read_text(encoding="utf-8")
    for text in (TOOL, sim):                         # no path to a real key file is spelled, and none is ever made
        assert f'"{desk_api.KEY_FILE}"' not in text and f'"{desk_api.LAB_KEY_FILE}"' not in text
        assert "ensure_key" not in text.replace("nothing here calls desk_api.ensure_key", "")
        assert "desk_api.KEY_FILE)" not in text.replace("(desk_api.KEY_FILE, desk_api.LAB_KEY_FILE)", "")


# ---------------------------------------------------------------- its clock is the replayed stream's
def test_the_clock_is_the_tick_streams_a_print_moves_it_on_and_only_the_streams_own_clock_moves_it_back():
    c = StreamClock()
    wall = dt.datetime.now(dt.timezone.utc)
    assert abs((c() - wall).total_seconds()) < 5                 # nothing heard yet (main never builds a Desk then)
    c.heard(at("09:20:00"))
    assert c().astimezone(host.ET).strftime("%Y-%m-%d %H:%M:%S") == "2026-09-14 09:20:00"
    c.saw(at("09:20:05"))
    c.saw(at("09:20:03"))                                        # an older print never moves time back
    assert c().astimezone(host.ET).strftime("%H:%M:%S") == "09:20:05"
    c.heard(at("09:20:01"))                                      # the stream's own clock may (a replay that restarts)
    assert c().astimezone(host.ET).strftime("%H:%M:%S") == "09:20:01"


def test_the_date_the_last_entry_time_and_the_flat_time_are_read_on_the_replayed_clock(tmp_path):
    d = Lab(tmp_path)
    assert d.ld.snapshot()["date"] == DATE == d.eng._today() != dt.date.today().isoformat()
    wrong = {**d.body(entry(1)), "date": dt.date.today().isoformat()}
    assert run(d.ld.event(wrong))["results"][0]["refused"] == labdesk_mod.OUT_OF_DATE     # the wall clock's day
    d.send(entry(2, price=110.0, sl=105.0, tp=None))
    d.prints([110.0])
    assert d.st().status == "live"
    run(d.rig.take(("clock", at("11:01:00"))))                   # past "no new trade after" (11:00), by the stream
    assert d.send(entry(3), last=110.0)["results"][0]["refused"] is not None and len(d.working()) == 1
    run(d.rig.take(("clock", at("15:54:59"))))
    d.tick()
    assert d.st().status == "live" and d.journal("clock_flat") == []
    run(d.rig.take(("clock", at("15:55:00"))))                   # the flat time, by the stream
    d.tick()
    assert d.journal("clock_flat")[0]["actions"][0] == "market Sell 1: ok"
    d.t = at("15:55:00")
    d.prints([111.0])
    assert (d.st().status, d.st().exit_reason) == ("done", "flat") and d.net() == 0


# ---- final fix wave: B5 N1-N3 ----------------------------------------------------------------------------------
class _Sock:
    """socket.socket in a test: records what bind_port asks of it; no real socket is made."""
    made: list = []

    def __init__(self, *a):
        self.calls, self.taken = [], False
        _Sock.made.append(self)

    def setsockopt(self, *a):
        self.calls.append(("setsockopt", a))

    def bind(self, addr):
        self.calls.append(("bind", addr))
        if self.taken:
            raise OSError("in use")

    def listen(self, *a):
        self.calls.append(("listen", a))

    def close(self):
        self.calls.append(("close",))


def test_the_practice_desk_binds_127_0_0_1_only_and_listens_at_once(monkeypatch):
    """B5 N1 / N2: the address is pinned; the port is listening straight after the bind, so a second start cannot
    bind it in the window before the server runs."""
    import socket
    _Sock.made = []
    monkeypatch.setattr(socket, "socket", _Sock)
    s = fake_desk.bind_port(8859)
    assert s is _Sock.made[0]
    names = [c[0] for c in s.calls]
    assert ("bind", ("127.0.0.1", 8859)) in s.calls
    assert names.index("listen") == names.index("bind") + 1
    assert "close" not in names


def test_a_taken_port_is_closed_and_none(monkeypatch):
    import socket

    class Taken(_Sock):
        def bind(self, addr):
            self.calls.append(("bind", addr))
            raise OSError("in use")
    _Sock.made = []
    monkeypatch.setattr(socket, "socket", Taken)
    assert fake_desk.bind_port(8859) is None
    assert [c[0] for c in _Sock.made[0].calls][-1] == "close"


def test_the_config_guard_reads_the_configs_own_mark_never_an_attribute_made_up_on_the_fly(tmp_path, monkeypatch):
    """B5 N3: a stand-in config whose every attribute answers (a Mock) is not a practice Desk's; only a config whose
    own fields carry the mark is. The guard is put on a recorder here: nothing is ever written."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import homebase.config as config_mod
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    saved = []
    monkeypatch.setattr(config_mod, "save", lambda cfg: saved.append(cfg))
    fake_desk.guard_config_save()
    mock = MagicMock()
    assert getattr(mock, "_practice_desk", False)                       # it answers every attribute
    config_mod.save(mock)
    assert saved == [mock]
    marked = SimpleNamespace()
    marked.__dict__["_practice_desk"] = True
    with pytest.raises(RuntimeError, match="practice Desk's config is never saved"):
        config_mod.save(marked)
    assert saved == [mock] and not (tmp_path / "config.json").exists()
