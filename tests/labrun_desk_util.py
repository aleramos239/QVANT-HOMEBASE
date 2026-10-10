"""Shared pieces for the runner's desk-mode tests (Step B, task B4): a stub Desk that answers the way the real one
does (homebase/labdesk.py: one row an intent), snapshots shaped like its stream's, and a StrategyDay hosted in desk
mode on hand-fed prints. No socket, no service: `send` is a method of the stub."""
from __future__ import annotations

from homebase.labrun.deskside import DeskSide, desk_id
from homebase.labrun.host import StrategyDay
from tests.test_labrun_host import D, HEAD, at, ms_of, plain, rec, ticks

NAME = "lab_x"                               # the store name the host tests use; on the Desk it is lab_lab_x
DESK_ID = desk_id(NAME)
DATE = D.isoformat()
ACCOUNT = "a1"

# One trade a day, and it says what it sees: every bar plots the order's status, `flat`, and its fill.
ONE = HEAD + '''class One(Strategy):
    id, name, root = "o", "One", "NQ"
    bar_minutes = 1
    bar_window = ("09:30", "09:40")

    def times(self):
        return ["09:30:00", "09:33:00", "15:50"]

    def on_session(self, ctx):
        self.o = None

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            self.o = ctx.stop_entry("long", ctx.last_price + 5, sl=ctx.last_price - 5, tp_rr=2.0)
        elif et_time == "09:33:00":
            if self.o.status == "working":
                ctx.cancel(self.o)
        else:
            ctx.flatten("time")

    def on_bar(self, ctx, bar):
        ctx.plot("status " + (self.o.status if self.o else "none"), ctx.now_ns, 1.0 if ctx.flat else 0.0)
        if self.o is not None and self.o.fill_px is not None:
            ctx.plot("fill", ctx.now_ns, self.o.fill_px)
'''

# An entry at every whole minute from 09:30 to 09:34 while it is flat (each with a stop), and a flatten at 09:35.
EVERY = HEAD + '''class Every(Strategy):
    id, name, root = "e", "Every", "NQ"

    def times(self):
        return ["09:30:00", "09:31:00", "09:32:00", "09:33:00", "09:34:00", "09:35:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:35:00":
            ctx.flatten("time")
        else:
            ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
'''

# Cancels its resting order and sends a new one in the SAME event (09:31), then flattens (09:32).
REPLACE = HEAD + '''class Replace(Strategy):
    id, name, root = "r", "Replace", "NQ"

    def times(self):
        return ["09:30:00", "09:31:00", "09:32:00"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            self.o = ctx.stop_entry("long", ctx.last_price + 5, sl=ctx.last_price - 5)
        elif et_time == "09:31:00":
            ctx.cancel(self.o)
            self.o = ctx.stop_entry("long", ctx.last_price + 6, sl=ctx.last_price - 4)
        else:
            ctx.flatten("time")
'''


def mark_of(source: str) -> list:
    r = rec(source)
    return [r["sha256"], r["promoted_utc"]]


def filled(px=21005.25, sl=20995.25, tp=21025.25, ms=None):
    return {"status": "filled", "fill_px": px, "fill_sl": sl, "fill_tp": tp, "fill_ms": ms or ms_of("09:30:30")}


def rnd(n=1, status="done", side="Buy", qty=1, entry=21005.25, exit_=21025.25, reason="tp", pnl=400.0,
        entry_t="09:30:30", exit_t="09:40:00", account=ACCOUNT, **kw):
    return {"account": account, "round": n, "status": status, "date": DATE, "carried": False, "iid": {side: n},
            "qty": qty, "entry_side": side, "entry_qty": qty, "entry_fill": entry, "exit_qty": qty if exit_ else 0,
            "exit_fill": exit_, "exit_reason": reason, "sl": 20995.25, "tp": 21025.25, "pnl": pnl, "clean": True,
            "entry_ms": ms_of(entry_t), "exit_ms": ms_of(exit_t) if exit_ else None, "why": None, **kw}


def snap(source=ONE, orders=None, flat=True, answered=(), rounds=(), **kw):
    """One strategy's whole snapshot, as the Desk's stream sends it (labdesk._snap)."""
    orders = orders or {}
    return {"strategy": DESK_ID, "mark": mark_of(source), "date": DATE, "enabled": True, "armed": True, "killed": False,
            "stopped": None, "rounds": list(rounds), "answered": list(answered),
            "brain": {"flat": flat, "working": sum(1 for o in orders.values() if o["status"] == "working"),
                      "entries_today": 0, "orders": {str(k): v for k, v in orders.items()}}, **kw}


class StubDesk:
    """The Desk's intake as the runner meets it: send(body) -> its answer. By default every intent is taken by the
    one account. `script`: answers for the next requests, in order (a dict is returned as it is; a callable gets the
    body; "took" = the default; an Exception is the transport's failure, as DeskClient reports it)."""
    NO_ANSWER = {"ok": False, "left": True, "status": None, "detail": None}

    def __init__(self, *script):
        self.bodies: list[dict] = []
        self.script = list(script)
        self.said: list[dict] = []                   # every heartbeat body the runner handed over (DeskClient.say)

    def say(self, body: dict) -> None:
        self.said.append(body)

    def take(self, body: dict) -> dict:
        rows = []
        for it in body["intents"]:
            op = it["op"]
            if op == "entry":
                rows.append({"op": op, "id": it["id"], "refused": None, "status": "working",
                             "accounts": {ACCOUNT: {"ok": True, "round": 1, "reason": None}}})
            elif op == "oco":
                rows.append({"op": op, "ids": list(it["ids"]), "refused": None})
            elif op == "cancel":
                rows.append({"op": op, "id": it["id"], "refused": None,
                             "accounts": {ACCOUNT: {"ok": True, "state": "cancelled", "actions": []}}})
            else:
                rows.append({"op": op, "refused": None, "accounts": {ACCOUNT: {"ok": True, "sold": 0, "actions": []}}})
        return {"ok": True, "seq": body["seq"], "results": rows, "brain": None}

    def refuse(self, sentence: str):
        """An answer in which no account took any entry, each with this sentence."""
        def answer(body):
            got = self.take(body)
            for r in got["results"]:
                if r["op"] == "entry":
                    r.update(status="cancelled", refused=sentence,
                             accounts={ACCOUNT: {"ok": False, "round": None, "reason": sentence}})
            return got
        return answer

    def send(self, body: dict, timeout: float = 5.0) -> dict:
        self.bodies.append(body)
        nxt = self.script.pop(0) if self.script else "took"
        if nxt == "took":
            return self.take(body)
        return nxt(body) if callable(nxt) else dict(nxt)

    # ---- what the tests read
    def ops(self) -> list:
        return [[it["op"] for it in b["intents"]] for b in self.bodies]

    def entries(self) -> list:
        """Every entry intent that ever left, in order."""
        return [it for b in self.bodies for it in b["intents"] if it["op"] == "entry"]


class Wall:
    """The runner's own clock, moved by hand."""

    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def desk_day(source=ONE, stub=None, *, up=True, accounts=(ACCOUNT,), resume=None, tells=None, now_ns=None, flat=True,
             **kw):
    """A StrategyDay in desk mode. up: the Desk's stream has sent this strategy's snapshot (it is answering).
    -> day, stub, side, the tell-log's lines, the wall clock."""
    stub = stub if stub is not None else StubDesk()
    wall = kw.pop("wall", None) or Wall()
    side = DeskSide(DESK_ID, mark_of(source), DATE, list(accounts), wall=wall, flat=flat)
    if up:
        side.take(snap(source, flat=flat) if up is True else up)
    tells = tells if tells is not None else []
    day = StrategyDay(rec(source), D, spawn=plain, daily=[], deadline_s=kw.pop("deadline_s", 0.3), desk=side,
                      send=stub.send, tell=tells.append, resume=resume, wall=wall, now_ns=now_ns, **kw)
    return day, stub, side, tells, wall


def feed(day, start: str, prices, step_ms: int = 1000) -> None:
    """Prints, then the stream's clock at the last one (what the runner hands a day)."""
    rows = ticks(start, prices, step_ms)
    day.on_ticks(rows)
    day.on_clock(rows[-1][0] // 1_000_000)


def plots(day) -> dict:
    """What the child said it saw (its plots land in the day's tape model in desk mode too)."""
    return day.fills.result.plots


LIMITS = {"max_trades_day": 3, "max_qty": 2, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}


def sidecar(source=ONE, accounts=(ACCOUNT,), **kw) -> dict:
    """The Desk's sidecar for the strategy (labcfg: mark, limits, book)."""
    return {"mark": mark_of(source), "limits": dict(LIMITS), "book": [{"account": a, "qty": 1} for a in accounts],
            "written_utc": "2026-10-10T08:00:00+00:00", **kw}


def state(*snaps, date=DATE) -> tuple:
    """The stream's first event, as DeskClient puts it on the runner's queue."""
    return ("desk", "state", {"date": date, "armed": True, "strategies": {s["strategy"]: s for s in snaps}})


__all__ = ["LIMITS", "sidecar", "state", "ACCOUNT", "D", "DATE", "DESK_ID", "EVERY", "NAME", "ONE", "REPLACE", "StubDesk", "Wall", "at", "desk_day",
           "feed", "filled", "mark_of", "ms_of", "plots", "rec", "rnd", "snap", "ticks"]
