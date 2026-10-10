"""An intent's shape: what a Lab strategy's child may ask for, checked field by field (2026-10-10).

well_formed() was the host's (labrun/host.py, Step A); it lives here so the desk can check a runner's event with the
very same rule without loading the tester (the host imports the backtest package, the desk must not). The intents
are the ones contracts.md writes: entry, oco, cancel, flatten, plot, hline, skip.

well_formed_stop() is the one op the RUNNER adds on the way to the desk (Step B, design C2) and a child can never
send: {"op": "stop", "why": str, "flatten": bool} -- the strategy is stopped for today; flatten says whether its
open trade is closed at once (it crashed or hung) or keeps its stop and the flat time (switched off, runner going).

Stdlib only; imports nothing from homebase.
"""
from __future__ import annotations

ORDER_OPS = ("entry", "oco", "cancel", "flatten")        # the intents that are orders (the rest are drawings / notes)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _opt(v) -> bool:
    return v is None or _num(v)


def well_formed(it) -> bool:
    """An intent as contracts.md writes it. The child is our code, but what it prints is not trusted."""
    if not isinstance(it, dict):
        return False
    op = it.get("op")
    if op == "entry":
        return (_int(it.get("id")) and it.get("kind") in ("market", "stop", "limit") and it.get("side") in ("long", "short")
                and (_num(it.get("price")) if it["kind"] != "market" else it.get("price") is None)
                and _int(it.get("qty")) and 1 <= it["qty"] <= 10_000 and isinstance(it.get("move"), bool)
                and all(_opt(it.get(k)) for k in ("sl", "tp", "tp_rr", "ref")))
    if op == "oco":
        return isinstance(it.get("ids"), list) and bool(it["ids"]) and all(_int(i) for i in it["ids"])
    if op == "cancel":
        return _int(it.get("id"))
    if op in ("flatten", "skip"):
        return isinstance(it.get("reason"), str)
    if op == "plot":
        return isinstance(it.get("name"), str) and _int(it.get("t_ms")) and _num(it.get("value"))
    if op == "hline":
        return (isinstance(it.get("name"), str) and _num(it.get("price")) and isinstance(it.get("role"), str)
                and _int(it.get("t_ms")))
    return False


def well_formed_stop(it) -> bool:
    """The runner's own intent: stop this strategy for today."""
    return (isinstance(it, dict) and it.get("op") == "stop" and isinstance(it.get("why"), str)
            and isinstance(it.get("flatten"), bool))
