"""One strategy brain over every account's rounds (Step B, design D8 and C5; 2026-10-10).

A promoted Lab strategy sends ONE entry and the desk's engine places it on every account booked to it, each in its
own round. The strategy's code knows nothing of accounts: it sees one order that is working, filled or cancelled, and
one `flat`. brain() makes that single view from the engine's rows (engine.lab_rounds), and both sides import it -- the
desk (its checks, the stream) and the runner (what the child is told) -- so they can never disagree.

    brain(rounds, entries_today) -> {"flat": bool, "working": int, "entries_today": int,
                                     "orders": {"<the strategy's order id>": {"status": "working" | "cancelled"}
                                                | {"status": "filled", "fill_px", "fill_sl", "fill_tp", "fill_ms"}}}

    filled      the first account whose leg of that order is wholly filled, or part filled with its round over;
                fill_px / fill_sl / fill_tp / fill_ms are that account's (the levels that rest at its broker)
    cancelled   its leg ended with no fill on every account that took it (cancelled, rejected), or the other leg of
                its pair filled first on any account
    working     otherwise
    flat        no account has a live round, and no account still rests a leg of an order already reported filled
    working     how many orders are still `working`

Known and accepted (design I, question 15): a pair can fill opposite legs on two accounts in a whipsaw. The brain
reports the first fill and calls the other leg cancelled, while that account still holds a position: `flat` stays
False until it is out.

A row marked `carried` is a block from an earlier day, not one of today's trades: it is left out. When one account
used an order id in two rounds, its latest round speaks. An order no account took has no row at all: the desk adds it
to its own snapshot as cancelled. Rows that do not read never raise.

Stdlib only; imports nothing from homebase.
"""
from __future__ import annotations

SIDES = ("Buy", "Sell")
OPEN = ("placing", "placed", "live")         # a round the engine still acts on
OVER = ("done", "error")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _leg(r: dict, side: str, n: int) -> dict:
    """One account's leg of one order, from its round's row: working | filled | cancelled."""
    status, qty = r.get("status"), r.get("qty")
    got = r["entry_qty"] if _int(r.get("entry_qty")) else 0
    held = r.get("entry_side") if r.get("entry_side") in SIDES and got > 0 else None    # the side that filled
    cancelled = r.get("cancelled") if isinstance(r.get("cancelled"), (list, tuple)) else ()
    if held == side and (status in OVER or not _int(qty) or got >= qty):
        state = "filled"
    elif status in OVER or side in cancelled or (held is not None and held != side):
        state = "cancelled"                  # ended with no fill, or the pair's other leg filled on this account
    else:
        state = "working"                    # resting, part filled with the rest still out, or a status unknown
    ms = r.get("entry_ms")
    return {"state": state, "n": n, "ms": ms if _int(ms) or isinstance(ms, float) else None,
            "px": r.get("entry_fill"), "sl": r.get("sl"), "tp": r.get("tp")}


def _first(leg: dict) -> tuple:
    """Which fill came first: by its time, then by the order of the rows (the engine gives them oldest first)."""
    return (leg["ms"] is None, leg["ms"] or 0, leg["n"])


def brain(rounds, entries_today) -> dict:
    legs: dict = {}                          # order id -> {account: its leg, from the account's latest round}
    pair: dict = {}                          # order id -> the other leg of its pair
    live = False
    for n, r in enumerate(rounds if isinstance(rounds, (list, tuple)) else ()):
        if not isinstance(r, dict) or r.get("carried"):
            continue
        live = live or r.get("status") == "live"
        iid = r.get("iid") if isinstance(r.get("iid"), dict) else {}
        ids = {s: iid[s] for s in SIDES if _int(iid.get(s))}
        if len(ids) == 2 and ids["Buy"] != ids["Sell"]:
            pair[ids["Buy"]], pair[ids["Sell"]] = ids["Sell"], ids["Buy"]
        for side, i in ids.items():
            legs.setdefault(i, {})[r.get("account")] = _leg(r, side, n)
    fills = {}                               # order id -> the first account's filled leg
    for i, by in legs.items():
        got = [g for g in by.values() if g["state"] == "filled"]
        if got:
            fills[i] = min(got, key=_first)
    orders: dict = {}
    for i, by in legs.items():
        mine, other = fills.get(i), fills.get(pair.get(i))
        if mine is not None and (other is None or _first(mine) <= _first(other)):
            orders[str(i)] = {"status": "filled", "fill_px": mine["px"], "fill_sl": mine["sl"],
                              "fill_tp": mine["tp"], "fill_ms": mine["ms"]}
        elif other is not None or all(g["state"] == "cancelled" for g in by.values()):
            orders[str(i)] = {"status": "cancelled"}
        else:
            orders[str(i)] = {"status": "working"}
    resting = any(g["state"] == "working" for i, by in legs.items() if orders[str(i)]["status"] == "filled"
                  for g in by.values())
    return {"flat": not live and not resting,
            "working": sum(1 for o in orders.values() if o["status"] == "working"),
            "entries_today": entries_today if _int(entries_today) else 0, "orders": orders}
