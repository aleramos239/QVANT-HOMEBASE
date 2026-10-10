"""DeskSide: one strategy's day as the Desk tells it (Step B, task B4; 2026-10-10).

In desk mode a promoted strategy's orders go to the Desk (labrun/deskclient.py) and everything the strategy's child is
told about them comes back from the Desk: nothing is modelled here. The Desk's stream is LEVEL TRIGGERED -- every
event is one strategy's whole snapshot (homebase/labdesk.py, _snap) -- so DeskSide keeps the latest one and, before
each event of the child, says what changed against what the child was last told. A reconnect needs nothing replayed.

    take(snapshot)     the latest word. One whose mark or date is not this day's is IGNORED, and the Desk counts as
                       silent for this strategy until one arrives that is.
    flat               the snapshot's brain.flat (the Desk folded every account into one answer: labrun/fanout.py)
    updates()          one update per order whose status or fill is not what the child was told
    trades()           the lead account's finished rounds of today, as the tester's trade rows
    silent()           the stream is down, holds nothing of this day for us, or said nothing for 15 s

WHAT A SNAPSHOT MAY SAY ABOUT AN ORDER. The stream is read by a thread of its own, so a snapshot can be OLDER than the
runner's last request: it does not list an order the Desk had not been sent yet, and that is not "cancelled". The
Desk's snapshot carries `answered`, the events (`seq`) it has answered today, and it never takes the entries of an
event below one it has answered. So for an order last touched by event `seq` (the entry itself, or a cancel / flatten
of it), a snapshot speaks only when it has answered `seq`, or a later event. When it speaks: the order reads as
brain.orders has it, and an order the child still believes working that it does not list at all is cancelled (no
account ever held it). That one rule also resolves an entry whose answer never came: the child is told nothing new
about it until a snapshot speaks.

A row of `rounds` marked `carried` is a block from an earlier day, not one of today's trades: trades() never returns
it. The lead account is the first account of the Desk's book for this strategy that has a round today.

Also here, because the runner must import nothing the Desk owns: the desk id of a store name (PREFIX: a test holds it
equal to homebase.labcfg.PREFIX) and booked(), which reads the Desk's sidecar the way the Desk does.

Stdlib and labrun.store only. Nothing here sends anything.
"""
from __future__ import annotations

import math
import re
import time

from . import store

PREFIX = "lab_"                  # desk id = PREFIX + the store name (homebase.labcfg.PREFIX: tests hold them equal)
SILENT_S = 15.0                  # nothing on the Desk's stream for this long: it is not answering
FIELDS = ("status", "fill_px", "fill_sl", "fill_tp", "fill_ms")      # what an update carries (shadowfills.FIELDS)
WORKING, CANCELLED = ("working", None, None, None, None), ("cancelled", None, None, None, None)
SIDE = {"Buy": "long", "Sell": "short"}
FLAT_LATEST = "15:55"            # the Desk's own bound on the flat time (labcfg.FLAT_LATEST)
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def desk_id(name: str) -> str:
    """The name a promoted strategy has on the Desk and on the wire."""
    return PREFIX + name


def _whole(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def _hhmm(v) -> bool:
    return isinstance(v, str) and _HHMM.fullmatch(v) is not None


def limits_read(limits, rec: dict) -> bool:
    """Limits as the Desk itself would take them (labcfg.parse_limits; a test runs both over the same cases). Limits
    that do not read are no limits, and with no limits there is no book."""
    if not isinstance(limits, dict):
        return False
    w = rec.get("session_window")
    start = w[0] if isinstance(w, (list, tuple)) and len(w) == 2 and _hhmm(w[0]) and _hhmm(w[1]) else store.DEFAULT_WINDOW[0]
    trades, qty, risk = limits.get("max_trades_day"), limits.get("max_qty"), limits.get("max_risk_usd")
    last, flat = limits.get("last_entry_et"), limits.get("flat_et")
    return (_whole(trades) and 1 <= trades <= 20 and _whole(qty) and 1 <= qty <= 10
            and _num(risk) and 0 < risk <= 1e9 and _hhmm(last) and _hhmm(flat) and flat <= FLAT_LATEST
            and start <= last < flat)


def booked(side, rec: dict) -> list | None:
    """The accounts a strategy trades on, in the order of the Desk's book, when its sidecar lets a day run in desk
    mode: it reads, it was written for THIS promotion of the record, its limits read, and its book is not empty.
    None for anything else (the day is hosted in shadow): an unreadable sidecar or unreadable limits are no book."""
    if not isinstance(side, dict) or not isinstance(rec, dict) or side.get("mark") != store.mark_of(rec):
        return None
    if not limits_read(side.get("limits"), rec) or not isinstance(side.get("book"), list):
        return None
    out = []
    for r in side["book"]:
        if isinstance(r, dict) and isinstance(r.get("account"), str) and r["account"] and r["account"] not in out \
                and _whole(r.get("qty")) and r["qty"] > 0:
            out.append(r["account"])
    return out or None


class DeskSide:
    """desk_id / mark / date: the day this side speaks for (a snapshot of another is ignored). accounts: the Desk's
    book for it, in order (the runner keeps it up to date: it only decides the lead). flat: what the day believes
    before the first snapshot (a day picked up from its tell-log: the log's last word)."""

    def __init__(self, desk_id: str, mark, date: str, accounts, *, wall=time.monotonic, flat: bool = True):
        self.desk_id, self.mark, self.date = desk_id, list(mark), date
        self.accounts = list(accounts)
        self._wall = wall
        self._snap: dict | None = None               # the latest snapshot of this day
        self._valid = False                          # ... and the Desk's latest word about us WAS one
        self._down = True                            # the stream is not open
        self._heard = float("-inf")                  # when it last said anything
        self._flat = bool(flat)
        self._orders: dict[int, list] = {}           # the child's entry id -> [the last event that touched it, what
                                                     # the child was last told (or believes): a FIELDS tuple]
        self._dead: set[int] = set()                 # entries the Desk will never hold

    # ---- the stream
    def heard(self) -> None:
        """Anything arrived on the stream: it is open and alive."""
        self._down, self._heard = False, self._wall()

    def down(self) -> None:
        """The stream ended. What it said before is kept (flat, the orders, the trades), but the Desk is not answering
        for us until a new stream has sent this strategy's snapshot again (a new stream starts with a whole state)."""
        self._down, self._valid = True, False

    def gone(self) -> None:
        """A whole state arrived that does not list this strategy: the Desk says nothing of this day for us."""
        self._valid = False

    def take(self, snap) -> bool:
        if not isinstance(snap, dict) or snap.get("strategy") != self.desk_id:
            return False
        self.heard()
        if snap.get("mark") != self.mark or snap.get("date") != self.date:
            self._valid = False                      # another promotion's, or another day's: nothing of it is believed
            return False
        self._snap, self._valid = snap, True
        brain = snap.get("brain")
        if isinstance(brain, dict) and isinstance(brain.get("flat"), bool):
            self._flat = brain["flat"]
        return True

    def silent(self) -> bool:
        return self._down or not self._valid or self._wall() - self._heard > SILENT_S

    # ---- what the Desk says (the latest snapshot of this day)
    @property
    def flat(self) -> bool:
        return self._flat

    @property
    def killed(self) -> bool:
        return self._snap is not None and self._snap.get("killed") is True

    @property
    def stopped(self) -> str | None:
        got = self._snap.get("stopped") if self._snap is not None else None
        return got if isinstance(got, str) else None

    @property
    def answered(self) -> list:
        """The events (`seq`) the Desk has answered today."""
        got = self._snap.get("answered") if self._snap is not None else None
        return sorted(a for a in got if _whole(a)) if isinstance(got, list) else []

    def seen(self) -> bool:
        """A snapshot of this day has arrived."""
        return self._snap is not None

    # ---- what the child did and was told
    def sent(self, seq: int, intents) -> None:
        """The child's order intents of event `seq`, in call order (also the ones that will not be sent). What the
        child believes right after: a new entry is working; a cancel, and a flatten for every working order, is
        cancelled (livectx.LiveCtx)."""
        for it in intents:
            op = it.get("op")
            if op == "entry":
                self._orders[it["id"]] = [seq, WORKING]
            elif op == "cancel" and it.get("id") in self._orders:
                o = self._orders[it["id"]]
                if o[1][0] == "working":
                    o[0], o[1] = seq, CANCELLED
            elif op == "flatten":
                for o in self._orders.values():
                    if o[1][0] == "working":
                        o[0], o[1] = seq, CANCELLED

    def dead(self, ids) -> None:
        """Entries that are not at the Desk and never will be: refused here and never sent, or refused there."""
        self._dead.update(i for i in ids if i in self._orders)

    def told(self, updates) -> None:
        """What a child was told before (the replay of a tell-log): believe the same."""
        for u in updates if isinstance(updates, list) else ():
            if isinstance(u, dict) and u.get("id") in self._orders:
                self._orders[u["id"]][1] = tuple(u.get(k) for k in FIELDS)

    def working(self) -> list:
        """The entries the child believes are working."""
        return [i for i, o in self._orders.items() if o[1][0] == "working"]

    def _says(self, i: int, seq: int, was: tuple, orders, answered: set, newest: int) -> tuple | None:
        """What the snapshot says about one order, or None: no news."""
        if i in self._dead:
            return CANCELLED
        if orders is None or not (seq in answered or newest > seq):
            return None                              # no snapshot of this day, or one older than the order's last event
        o = orders.get(str(i))
        if o is None:
            return CANCELLED if was[0] == "working" else None
        status = o.get("status") if isinstance(o, dict) else None
        if status == "filled":
            return (status, *(o.get(k) for k in FIELDS[1:]))
        return {"working": WORKING, "cancelled": CANCELLED}.get(status)

    def updates(self) -> list[dict]:
        """One update per order whose status or fill is not what the child was last told, in the order the child
        made them."""
        # (the latest snapshot of THIS day, also while the stream is down: what the Desk said happened did happen)
        brain = self._snap.get("brain") if self._snap is not None else None
        orders = brain.get("orders") if isinstance(brain, dict) and isinstance(brain.get("orders"), dict) else None
        answered = set(self.answered)
        newest = max(answered, default=-1)
        out = []
        for i, o in self._orders.items():
            now = self._says(i, o[0], o[1], orders, answered, newest)
            if now is not None and now != o[1]:
                o[1] = now
                out.append({"id": i, **dict(zip(FIELDS, now))})
        return out

    # ---- the day's real trades
    def _rows(self) -> list:
        """Today's rounds (never a carried block, never another date's), oldest first."""
        rows = self._snap.get("rounds") if self._snap is not None else None
        return [r for r in rows if isinstance(r, dict) and not r.get("carried") and r.get("date") == self.date] \
            if isinstance(rows, list) else []

    def lead(self) -> str | None:
        """The first account of the Desk's book that has a round today."""
        have = {r.get("account") for r in self._rows()}
        return next((a for a in self.accounts if a in have), None)

    def _lead_rows(self) -> list:
        lead = self.lead()
        return [r for r in self._rows() if r.get("account") == lead] if lead is not None else []

    @staticmethod
    def _entered(r: dict) -> bool:
        return r.get("entry_side") in SIDE and _whole(r.get("entry_qty")) and r["entry_qty"] > 0

    @staticmethod
    def _priced(r: dict) -> bool:
        return all(_num(r.get(k)) for k in ("entry_fill", "exit_fill", "entry_ms", "exit_ms"))

    def trades(self) -> list[dict]:
        """The lead account's finished trades of today, as the tester's rows (backtest.engine.Trade.to_dict: the keys
        the day summary and the daily match read). A round that never filled is not a trade; one still open is not a
        trade yet. `net` is the Desk's own figure for the round."""
        out = []
        for r in self._lead_rows():
            if r.get("status") == "done" and self._entered(r) and self._priced(r):
                out.append({"side": SIDE[r["entry_side"]], "qty": r["entry_qty"],
                            "entry_ns": int(r["entry_ms"]) * 1_000_000, "entry_price": r["entry_fill"],
                            "exit_ns": int(r["exit_ms"]) * 1_000_000, "exit_price": r["exit_fill"],
                            "exit_reason": r.get("exit_reason") if isinstance(r.get("exit_reason"), str) else "exit",
                            "net": r["pnl"] if _num(r.get("pnl")) else 0.0})
        return out

    def unpriced(self) -> int:
        """Lead-account trades that are over but whose fills the Desk does not hold (a time or a price is missing):
        they cannot be compared with a backtest."""
        return sum(1 for r in self._lead_rows()
                   if r.get("status") in ("done", "error") and self._entered(r) and not self._priced(r))
