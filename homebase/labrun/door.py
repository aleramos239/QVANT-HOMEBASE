"""The door: pure checks that say, in one sentence, why a Lab strategy's order would be refused (2026-10-09).

check() judges one intent, check_event() the intents of one event, read_source() reads a draft's text (AST only,
nothing runs) and returns notes for the owner. The sentences, in the order check() tries them:

    Limit entries are not built yet. / Every entry needs a stop held at the broker. / The stop must sit on the losing
    side of the entry. / Size is set on the Desk, per account. / One position at a time. / Daily limit reached (N trade[s]).
    / Too late for a new trade today. / Stop too far: $X at risk, limit $Y. / Prices are late.
    Only a buy-stop and sell-stop pair can be linked. (an oco, in check_event)
    The Desk cannot check this order. (the state or the limits cannot be read: an entry fails closed, before any other)
 Nothing here places an order, reads a file or talks to a service: the
host passes in the state and the limits and shows the sentence it gets back.

    state  = {"flat", "working_entries", "entries_today", "last_price", "now_hhmm", "prices_late"}
    limits = {"max_trades_day", "max_qty", "max_risk_usd" (0 = not set), "last_entry_et", "session_from_et",
              "point_value", "tick"}

Stdlib only; imports nothing from homebase.
"""
from __future__ import annotations

import ast
import math

NO_STOP = "Every entry needs a stop held at the broker."
WRONG_SIDE = "The stop must sit on the losing side of the entry."
NO_LIMIT = "Limit entries are not built yet."
ONE_AT_A_TIME = "One position at a time."
OWN_SIZE = "Size is set on the Desk, per account."
TOO_LATE = "Too late for a new trade today."
PRICES_LATE = "Prices are late."
NOT_A_PAIR = "Only a buy-stop and sell-stop pair can be linked."
CANNOT_CHECK = "The Desk cannot check this order."
STATE_KEYS = ("flat", "working_entries", "entries_today", "last_price", "now_hhmm", "prices_late")   # last_price may be None
LIMIT_KEYS = ("max_trades_day", "last_entry_et", "session_from_et", "max_risk_usd", "point_value")


def _entry_price(intent: dict, state: dict) -> float | None:
    """The price the stop and the risk are measured from: the order's own, else ref, else the last print."""
    if intent.get("kind") == "market":
        px = intent.get("ref")
        return px if px is not None else state.get("last_price")
    return intent.get("price")


def _wrong_side(intent: dict, px: float | None) -> bool:
    sl, tp = intent.get("sl"), intent.get("tp")
    side = intent.get("side")
    if px is None or side not in ("long", "short"):
        return True                                      # fail closed: nothing to measure the stop against
    s = 1 if side == "long" else -1
    return (px - sl) * s <= 0 or (tp is not None and (tp - px) * s <= 0)


def check(intent: dict, state: dict, limits: dict) -> str | None:
    """None = allowed, else the sentence for the first check that fails. Only entries can be refused here; an
    oco is judged with its entries in check_event. Fails closed: a state or limits it cannot read, or an entry
    it cannot make sense of, is refused ("The Desk cannot check this order."); it never raises."""
    if intent.get("op") != "entry":
        return None
    try:
        if (any(state.get(k, _MISSING) is _MISSING for k in STATE_KEYS)
                or any(state.get(k) is None for k in STATE_KEYS if k != "last_price")
                or any(limits.get(k) is None for k in LIMIT_KEYS)):
            return CANNOT_CHECK
        return _check_entry(intent, state, limits)
    except (TypeError, ValueError, KeyError, AttributeError, ArithmeticError):
        return CANNOT_CHECK


_MISSING = object()


def _check_entry(intent: dict, state: dict, limits: dict) -> str | None:
    if intent.get("kind") == "limit":
        return NO_LIMIT
    if intent.get("sl") is None:
        return NO_STOP
    px = _entry_price(intent, state)
    if _wrong_side(intent, px):
        return WRONG_SIDE
    if intent.get("own_qty"):
        return OWN_SIZE
    if not state.get("flat") or state.get("working_entries", 0) > 0:
        return ONE_AT_A_TIME
    n = limits["max_trades_day"]
    if state.get("entries_today", 0) >= n:
        return f"Daily limit reached ({n} trade{'' if n == 1 else 's'})."
    now = state.get("now_hhmm")
    if now > limits["last_entry_et"] or now < limits["session_from_et"]:
        return TOO_LATE
    cap = limits.get("max_risk_usd") or 0
    if cap > 0:
        risk = round(abs(px - intent["sl"]) * limits["point_value"] * intent["qty"], 6)
        if risk > cap:
            return f"Stop too far: ${math.ceil(risk):,} at risk, limit ${cap:,.0f}."
    if state.get("prices_late"):
        return PRICES_LATE
    return None


def _is_pair(oco: dict, entries: dict) -> bool:
    """Exactly one buy stop and one sell stop of the same size, both sent in this event."""
    ids = oco.get("ids")
    if not isinstance(ids, list) or len(ids) != 2 or ids[0] == ids[1]:
        return False
    a, b = (entries.get(i) for i in ids)
    if a is None or b is None:
        return False
    return (a.get("kind") == b.get("kind") == "stop" and {a.get("side"), b.get("side")} == {"long", "short"}
            and a.get("qty") == b.get("qty"))


def _used(st: dict) -> None:
    st["working_entries"] = st.get("working_entries", 0) + 1
    st["entries_today"] = st.get("entries_today", 0) + 1


def check_event(intents: list, state: dict, limits: dict) -> list[str | None]:
    """One verdict per intent, in order. An allowed entry uses the slot, so a second lone entry in the same event
    is refused. Two stop entries of opposite sides that one oco intent of the same event links are ONE trade:
    both legs are judged against the state before the pair, if either is refused BOTH get the first refused leg's
    sentence (a lone leg of a pair never goes out), and the oco's own verdict is None."""
    st = dict(state) if isinstance(state, dict) else {}
    entries = {i.get("id"): i for i in intents if i.get("op") == "entry"}
    pair_of: dict = {}                                   # entry id -> (the pair's ids, in order)
    out: list[str | None] = [None] * len(intents)
    for n, i in enumerate(intents):
        if i.get("op") != "oco":
            continue
        if _is_pair(i, entries):
            for leg in i["ids"]:
                pair_of.setdefault(leg, tuple(i["ids"]))
        else:
            out[n] = NOT_A_PAIR
    pairs: dict = {}                                     # a pair's ids -> its one verdict, judged at its first leg
    for n, i in enumerate(intents):
        if i.get("op") != "entry":
            continue
        key = pair_of.get(i.get("id"))
        if key is None:
            out[n] = check(i, st, limits)
            if out[n] is None:
                _used(st)
            continue
        if key not in pairs:
            first, other = entries[i["id"]], entries[key[1] if key[0] == i["id"] else key[0]]
            pairs[key] = check(first, st, limits) or check(other, st, limits)
            if pairs[key] is None:
                _used(st)
        out[n] = pairs[key]
    return out


# ---------------------------------------------------------------- reading a draft's text

_ORDER_CALLS = {"market": (2, 1), "stop_entry": (3, 2), "limit_entry": (3, 2)}   # name -> (sl, qty) positions


def _none_branch(node) -> bool:
    """sl=None, or a conditional with a None branch (sl=None if x else 5.0)."""
    if isinstance(node, ast.Constant):
        return node.value is None
    if isinstance(node, ast.IfExp):
        return _none_branch(node.body) or _none_branch(node.orelse)
    return False


def _arg(call: ast.Call, name: str, pos: int):
    """The node passed as `name` (keyword, else by position), or None when it is not passed.
    False when the call splats arguments and the answer cannot be read."""
    for k in call.keywords:
        if k.arg == name:
            return k.value
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return False
    return call.args[pos] if len(call.args) > pos else None


def read_source(text: str) -> list[str]:
    """Notes for the owner from the draft's text. Reads it with ast and runs nothing."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        return [f"The code does not read: {getattr(e, 'msg', None) or e}."]
    no_stop = limit = own_size = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _ORDER_CALLS):
            continue
        sl_pos, qty_pos = _ORDER_CALLS[node.func.attr]
        sl = _arg(node, "sl", sl_pos)
        if sl is None or (sl is not False and _none_branch(sl)):
            no_stop += 1
        qty = _arg(node, "qty", qty_pos)
        if qty is not None and qty is not False and not _none_branch(qty):
            own_size += 1
        limit += node.func.attr == "limit_entry"
    notes = []
    if no_stop:
        notes.append("1 order can go out with no stop." if no_stop == 1
                     else f"{no_stop} orders can go out with no stop.")
    if limit:
        notes.append("It uses limit entries: not built yet.")
    if own_size:
        notes.append("It sets its own size: size is set on the Desk.")
    return notes
