"""The Lab strategy's child process: hosts ONE strategy and speaks JSON lines (2026-10-09).

    python -m homebase.labrun.child     (the host launches it inside the macOS sandbox, as for any draft)

One JSON object a line on stdin, one reply a line on stdout (stderr is free text):
  {"op": "init", "name", "source", "params", "qty", "date"}  -> {"ok": true, "meta": {...}} | {"ok": false, "error"}
  {"op": "event", "kind": "session"|"bar"|"time", "t_ns", "arg", "last_price", "flat", "updates", ["daily"]}
                                                              -> {"ok": true, "intents": [...]} | {"ok": false, "error"}
  {"op": "stop"}                                               -> the child exits 0
The strategy runs against a LiveCtx: its orders come back as intents and nothing here places an order. A strategy's own
print() goes to stderr, so it can never corrupt a protocol line.
"""
from __future__ import annotations

import datetime as dt
import json
import sys

from ..backtest import drafthost
from ..backtest.engine import Bar
from ..contracts import point_value, tick_size
from .livectx import LiveCtx


def _init(msg: dict):
    """(strategy, ctx, meta) from an init line. Any failure raises."""
    day = dt.date.fromisoformat(msg["date"])
    strategy = drafthost.register_source(msg["name"], msg["source"])(msg.get("params") or {})
    root = strategy.root
    ctx = LiveCtx(root=root, date=day, tick=tick_size(root), point_value=point_value(root) or 0.0,
                  qty=int(msg["qty"]), daily=[])
    bw = strategy.bar_window
    meta = {"root": root, "session_window": list(strategy.session_window), "bar_minutes": strategy.bar_minutes,
            "bar_window": list(bw) if bw else None, "placement_ms": strategy.placement_ms,
            "times": list(strategy.times()), "needs_daily": bool(strategy.needs_daily()),
            "trades_on": bool(strategy.trades_on(day))}
    return strategy, ctx, meta


def _event(strategy, ctx: LiveCtx, msg: dict) -> list[dict]:
    kind = msg["kind"]
    if "flat" not in msg:
        raise ValueError("an event line needs flat")
    if kind == "session":
        ctx.daily = msg.get("daily") or []
    ctx.begin(msg["t_ns"], msg.get("last_price"), msg["flat"], msg.get("updates") or [])
    try:
        if kind == "session":
            strategy.on_session(ctx)
        elif kind == "bar":
            strategy.on_bar(ctx, Bar(**msg["arg"]))
        elif kind == "time":
            strategy.on_time(ctx, msg["arg"])
        else:
            raise ValueError(f"unknown event kind {kind!r}")
    except BaseException:
        ctx.drain()                  # what a crashed handler queued is dropped, as the tester drops a crashed session
        raise
    return ctx.drain()


def main() -> int:
    out = sys.stdout                 # the protocol's stdout; a strategy's print() goes to stderr from here on
    sys.stdout = sys.stderr

    def reply(obj: dict) -> None:
        try:
            line = json.dumps(obj, allow_nan=False)
        except (TypeError, ValueError) as e:
            line = json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})
        out.write(line + "\n")
        out.flush()

    strategy = ctx = None
    for raw in sys.stdin:
        try:
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                raise ValueError("a line is one JSON object")
            op = msg.get("op")
            if op == "stop":
                return 0
            if op == "init":
                try:
                    strategy, ctx, meta = _init(msg)
                except Exception as e:  # noqa: BLE001 -- the owner must see what broke
                    reply({"ok": False, "error": str(e) or type(e).__name__})
                    return 1
                reply({"ok": True, "meta": meta})
            elif op == "event":
                if strategy is None:
                    raise ValueError("event before init")
                reply({"ok": True, "intents": _event(strategy, ctx, msg)})
            else:
                raise ValueError(f"unknown op {op!r}")
        except Exception as e:  # noqa: BLE001 -- the host decides what a failed event means
            reply({"ok": False, "error": f"{type(e).__name__}: {e}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
