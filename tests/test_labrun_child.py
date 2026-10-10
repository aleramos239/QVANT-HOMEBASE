"""The sandboxed child, run for real as a subprocess: JSON lines in, JSON lines out."""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
T0 = 1_709_634_600_000_000_000          # 2024-03-05 09:30:00 ET, whatever: the child only echoes the clock

STRADDLE = '''
from homebase.strategies.base import Strategy


class Straddle(Strategy):
    id, name, root = "x", "Straddle", "NQ"
    session_window = ("09:25", "16:00")
    placement_ms = 40

    def times(self):
        return ["09:30:00", "15:55:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            px = ctx.last_price
            ctx.move_brackets_to_fill = True
            self.up = ctx.stop_entry("long", px + 10, sl=px, tp=px + 30)
            self.dn = ctx.stop_entry("short", px - 10, sl=px, tp=px - 30)
            ctx.oco(self.up, self.dn)
            ctx.hline("up", self.up.price, role="entry")
        else:
            ctx.plot("up_fill", ctx.now_ns, self.up.fill_px or -1.0)
            ctx.plot("dn_status_len", ctx.now_ns, float(len(self.dn.status)))
            ctx.plot("flat", ctx.now_ns, 1.0 if ctx.flat else 0.0)
            ctx.flatten()
            ctx.plot("flat_after", ctx.now_ns, 1.0 if ctx.flat else 0.0)
'''

BARS = '''
from homebase.strategies.base import Strategy


class Bars(Strategy):
    id, name, root = "b", "Bars", "GC"
    session_window = ("09:00", "12:00")
    bar_minutes = 5
    bar_window = ("09:00", "10:00")

    def needs_daily(self):
        return True

    def on_session(self, ctx):
        self.n = 0
        ctx.plot("daily", ctx.now_ns, float(len(ctx.daily)))

    def on_bar(self, ctx, bar):
        print("hello from the strategy")
        self.n += 1
        if self.n == 1 and ctx.flat:
            ctx.market("long", sl=bar.l, ref=bar.c)
        ctx.plot("flat", bar.end_ns, 1.0 if ctx.flat else 0.0)
        ctx.plot("close", bar.end_ns, bar.c)
'''

BOOM = '''
from homebase.strategies.base import Strategy


class Boom(Strategy):
    id, name, root = "k", "Boom", "NQ"

    def times(self):
        return ["09:30:00", "09:31:00"]

    def on_time(self, ctx, et_time):
        ctx.stop_entry("long", 100.0, sl=99.0)
        if et_time == "09:30:00":
            raise RuntimeError("boom")
        ctx.skip("fine")
'''

NAN_PLOT = '''
from homebase.strategies.base import Strategy


class NanPlot(Strategy):
    id, name, root = "n", "NanPlot", "NQ"

    def times(self):
        return ["09:30:00"]

    def on_time(self, ctx, et_time):
        ctx.plot("bad", ctx.now_ns, float("nan"))
        ctx.market("long", sl=ctx.last_price - 5)
'''

TWO = BOOM + '''

class Other(Strategy):
    id, name, root = "o", "Other", "NQ"
'''


class Child:
    def __init__(self):
        self.p = subprocess.Popen([sys.executable, "-m", "homebase.labrun.child"], cwd=REPO, text=True,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.out: queue.Queue = queue.Queue()
        self.err: str | None = None
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.out.put(line)
        self.out.put(None)

    def send_raw(self, text: str) -> str | None:
        self.p.stdin.write(text + "\n")
        self.p.stdin.flush()
        return self.out.get(timeout=30)

    def send(self, obj: dict) -> dict:
        line = self.send_raw(json.dumps(obj))
        assert line is not None and line.endswith("\n") and line.count("\n") == 1
        return json.loads(line)

    def init(self, source: str, name="lab_test", params=None, qty=2, date="2024-03-05") -> dict:
        return self.send({"op": "init", "name": name, "source": source, "params": params or {}, "qty": qty,
                          "date": date})

    def event(self, kind, arg=None, t_ns=T0, last_price=None, flat=True, updates=(), daily=None) -> dict:
        ev = {"op": "event", "kind": kind, "t_ns": t_ns, "arg": arg, "last_price": last_price, "flat": flat,
              "updates": list(updates)}
        if daily is not None:
            ev["daily"] = daily
        return self.send(ev)

    def stop(self) -> int:
        self.p.stdin.write(json.dumps({"op": "stop"}) + "\n")
        self.p.stdin.flush()
        return self.p.wait(timeout=30)

    def close(self) -> str:
        """Let the child end, return everything it wrote to stderr. Safe to call twice."""
        if self.err is None:
            try:
                self.p.stdin.close()
            except OSError:                          # the child already exited
                pass
            self.p.wait(timeout=30)
            self.err = self.p.stderr.read()
            self.p.stderr.close()
            self.p.stdout.close()
        return self.err


@pytest.fixture
def child():
    c = Child()
    yield c
    c.close()


def test_init_replies_with_the_meta_block(child):
    r = child.init(STRADDLE)
    assert r == {"ok": True, "meta": {"root": "NQ", "session_window": ["09:25", "16:00"], "bar_minutes": 0,
                                      "bar_window": None, "placement_ms": 40, "times": ["09:30:00", "15:55:00"],
                                      "needs_daily": False, "trades_on": True}}


def test_meta_of_a_bar_strategy(child):
    m = child.init(BARS)["meta"]
    assert (m["root"], m["bar_minutes"], m["bar_window"], m["needs_daily"], m["placement_ms"]) == \
           ("GC", 5, ["09:00", "10:00"], True, 85)


def test_a_scripted_straddle_day(child):
    child.init(STRADDLE)
    assert child.event("session", t_ns=T0 - 10, last_price=None) == {"ok": True, "intents": []}
    r = child.event("time", "09:30:00", t_ns=T0, last_price=100.0)
    assert r["ok"] is True
    up, dn, oco, line = r["intents"]
    assert up == {"op": "entry", "id": 1, "kind": "stop", "side": "long", "price": 110.0, "qty": 2,
                  "own_qty": False, "sl": 100.0, "tp": 130.0, "tp_rr": None, "ref": 110.0, "move": True}
    assert dn["side"] == "short" and dn["price"] == 90.0 and dn["id"] == 2
    assert oco == {"op": "oco", "ids": [1, 2]}
    assert line == {"op": "hline", "name": "up", "price": 110.0, "role": "entry", "t_ms": T0 // 1_000_000}


def test_updates_sent_before_an_event_are_visible_to_the_handler(child):
    child.init(STRADDLE)
    child.event("time", "09:30:00", last_price=100.0)
    fill = {"id": 1, "status": "filled", "fill_px": 110.25, "fill_sl": 100.25, "fill_tp": 130.25, "fill_ms": 5}
    r = child.event("time", "15:55:00", t_ns=T0 + 1_000_000_000, last_price=111.0, flat=False,
                    updates=[fill, {"id": 2, "status": "cancelled", "fill_px": None, "fill_sl": None,
                                    "fill_tp": None, "fill_ms": None}])
    plots = {i["name"]: i["value"] for i in r["intents"] if i["op"] == "plot"}
    assert plots == {"up_fill": 110.25, "dn_status_len": float(len("cancelled")), "flat": 0.0, "flat_after": 1.0}
    assert {"op": "flatten", "reason": "time"} in r["intents"]


def test_a_bar_strategy_gets_bars_daily_and_the_flat_flag(child):
    child.init(BARS)
    r = child.event("session", t_ns=T0, daily=[{"d": 1}, {"d": 2}, {"d": 3}])
    assert r["intents"] == [{"op": "plot", "name": "daily", "t_ms": T0 // 1_000_000, "value": 3.0}]
    bar = {"start_ns": T0, "end_ns": T0 + 300_000_000_000, "o": 10.0, "h": 12.0, "l": 9.5, "c": 11.0, "v": 77}
    r = child.event("bar", bar, t_ns=bar["end_ns"], last_price=11.0, flat=True)
    entry = r["intents"][0]
    assert entry["op"] == "entry" and entry["kind"] == "market" and entry["sl"] == 9.5 and entry["ref"] == 11.0
    assert entry["price"] is None and entry["qty"] == 2
    assert {"op": "plot", "name": "flat", "t_ms": bar["end_ns"] // 1_000_000, "value": 1.0} in r["intents"]
    r = child.event("bar", bar, t_ns=bar["end_ns"] + 1, last_price=11.0, flat=False)   # a position is open
    assert all(i["op"] == "plot" for i in r["intents"])
    assert {"op": "plot", "name": "flat", "t_ms": (bar["end_ns"] + 1) // 1_000_000, "value": 0.0} in r["intents"]


def test_a_strategy_print_does_not_break_the_protocol(child):
    child.init(BARS)
    child.event("session")
    bar = {"start_ns": T0, "end_ns": T0 + 1, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1}
    for _ in range(2):
        assert child.event("bar", bar)["ok"] is True
    assert child.stop() == 0
    assert "hello from the strategy" in child.close()


def test_a_raising_handler_answers_ok_false_and_the_child_keeps_going(child):
    child.init(BOOM)
    r = child.event("time", "09:30:00")
    assert r == {"ok": False, "error": "RuntimeError: boom"}
    r = child.event("time", "09:31:00")                  # the order queued before the raise is not carried over
    assert r["ok"] is True
    assert [i["op"] for i in r["intents"]] == ["entry", "skip"] and r["intents"][0]["id"] == 2


def test_a_bad_line_is_answered_and_skipped(child):
    child.init(STRADDLE)
    assert json.loads(child.send_raw("this is not json"))["ok"] is False
    assert json.loads(child.send_raw("[1, 2]"))["ok"] is False
    r = child.send({"op": "nope"})
    assert r["ok"] is False and "nope" in r["error"]
    assert child.event("session") == {"ok": True, "intents": []}


def test_an_event_before_init_is_refused(child):
    r = child.event("session")
    assert r["ok"] is False


def test_two_strategy_classes_fail_init_and_exit_1(child):
    r = child.init(TWO)
    assert r["ok"] is False and "exactly one Strategy subclass" in r["error"]
    assert child.p.wait(timeout=30) == 1


def test_a_broken_source_or_bad_params_fail_init(child):
    r = child.init("def (:\n")
    assert r["ok"] is False and "SyntaxError" in r["error"]
    assert child.p.wait(timeout=30) == 1
    c2 = Child()
    try:
        r = c2.init(STRADDLE, params={"nope": 1})
        assert r["ok"] is False and "unknown input" in r["error"]
        assert c2.p.wait(timeout=30) == 1
    finally:
        c2.close()


def test_stop_exits_zero(child):
    child.init(STRADDLE)
    assert child.stop() == 0


def test_stdin_closed_exits_zero(child):
    child.init(STRADDLE)
    child.p.stdin.close()
    assert child.p.wait(timeout=30) == 0


def test_an_event_without_flat_is_an_error_reply(child):
    child.init(STRADDLE)
    r = child.send({"op": "event", "kind": "session", "t_ns": T0, "arg": None, "last_price": None, "updates": []})
    assert r["ok"] is False and "flat" in r["error"]
    assert child.event("session") == {"ok": True, "intents": []}          # and the child still answers


def test_a_nan_plot_does_not_cost_the_events_order_intents(child):
    child.init(NAN_PLOT)
    r = child.event("time", "09:30:00", last_price=100.0)
    assert r["ok"] is True and [i["op"] for i in r["intents"]] == ["entry"]


@pytest.mark.parametrize("flat", [None, 1, 0, "yes", "true", [True]])
def test_an_event_whose_flat_is_not_a_boolean_is_an_error_reply(child, flat):
    child.init(STRADDLE)
    r = child.send({"op": "event", "kind": "session", "t_ns": T0, "arg": None, "last_price": None, "flat": flat,
                    "updates": []})
    assert r["ok"] is False and "flat" in r["error"]
    assert child.event("session", flat=False) == {"ok": True, "intents": []}
