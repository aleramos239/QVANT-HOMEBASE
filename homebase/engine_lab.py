"""THE LAB SECTION of the desk engine (Step B, task B2): several trades a day, for kind "lab" ONLY.

Engine (engine.py) inherits LabMixin: every method here is reached as engine._lab_* / engine.lab_* and reads the
Engine's own state (states, cfg, adapters, journal, _save, day_states, ...).

A promoted Lab strategy trades in ROUNDS. The open round of a (strategy, account) pair keeps the
plain key "strategy@account", so everything above works on it unchanged; a round that is over AND
clean is archived under "strategy@account#n" and never acted on again. Eight hooks in engine.py reach
this section, each only for cfg.kind == "lab" (or, for _archived, a state the plain key no longer
holds -- never true of another kind's state). Nothing here is reached by a straddle, bars or
levels strategy.

  I-1  one open round per pair, at the plain key
  I-2  a new round only when the last one is terminal AND clean: every order id it placed reads
       terminal at the broker. Otherwise no new entry on that account, and it says so
  I-3  the open (or last) round is the last-inserted state of its pair
  I-4  an archived round is never acted on again

What a round needs beyond its DayState (the strategy's own order ids, its legs, how it is being
closed, whether its orders were checked) lives in self._lab, saved to labday-<date>.json beside
the day file. It is read at the first Lab call, never at construction: a missing or unreadable
file cannot stop the desk from starting, and a round whose extras are lost is never clean.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

from .broker.base import BrokerAdapter, OrderRequest, OrderResult
from .config import StrategyCfg, assignments
from .contracts import tick_size
from .daystate import (KILL_POLL_N, KILL_POLL_S, MARKET_OUT_FAILED, PLACING_UNKNOWN, TERMINAL, WORKING, DayState,
                       _hhmm, _to_tick)

LAB = "lab"                                    # StrategyCfg.kind
LAB_PREFIX = "lab_"                            # a Lab strategy's desk id (labcfg.PREFIX: a test holds them equal)
LAB_FLAT_TEXT = "homebase:lab-flat"            # the capped market-out's order text
LAB_FLAT_RETRY_S = 5.0                         # the flat time's retry (cancels and reads only)
LAB_CHECK_RETRY_S = 30.0                       # ... once a round is "check it"
LAB_SETTLE_S = 2.0                             # a closed round's orders are re-read this often
LAB_SETTLE_FAST = 5                            # ... for this many reads, then every LAB_CHECK_RETRY_S
LAB_UNCONFIRMED_S = 5.0                        # a close with no exit fill is given this long
LAB_CLOCK_POLLS = 2                            # the clock's flatten re-reads an entry this often (250 ms apart)
# The sentences the owner reads (design, section E). The door's own are repeated here so the engine never
# imports the runner's code; tests/test_engine_lab.py holds them equal.
LAB_NOT_ON_DESK = "That strategy is not on the Desk."
LAB_OFF = "It is off."
LAB_KILLED = "Killed today."
LAB_DISARMED = "The desk is disarmed: written down only."
LAB_NOT_CONNECTED = "The account is not connected."
LAB_ACCOUNT_STOPPED = "This account is stopped for the day."
LAB_TAKE_RULE = "This account has a daily take rule. A Lab strategy cannot share it."
LAB_ONE_AT_A_TIME = "One position at a time."
LAB_SLOT_BUSY = "Another strategy's trade on this account is open or not checked yet."
LAB_CANNOT_CHECK = "The Desk cannot check the last trade's orders."
LAB_CLOSE_UNCONFIRMED = "Check it: the close order was not confirmed. Its stop is still working."
LAB_EXIT_TWICE = "Check it: this trade's exit may have filled twice."
LAB_NO_POSITION_READ = "The Desk cannot read this account's position."
LAB_NO_STOP_ID = "Check it: the Desk does not know this trade's stop order."
LAB_BAD_RECORD = "The Desk cannot read yesterday's record for this account."
LAB_OLD_ORDER_WORKING = "An old order of this trade is still working. Cancel it first."
LAB_LOST_ACT = "check it — this trade's record was lost: nothing is sent or cancelled for it"
LAB_NET_AGAIN_MS = 2000                        # a position read that disagrees counts again after this long (M2)
LAB_ID_FIELDS = ("upper_id", "lower_id", "up_sl_id", "up_tp_id", "dn_sl_id", "dn_tp_id")
LAB_NO_BLOCK = "This account has no block to clear."
# The ONLY failures of a single entry that leave its round clean: the adapters' own fixed phrases for a path that
# sends nothing, or for a broker answer that carries no order (homebase/broker/). Everything else is unknown.
LAB_CLEAR_REJECTS = (
    "adapter not connected",                                        # tradovate.py place_bracket / place_order: no socket
    "OSO rejected (no orderId returned)",                           # tradovate.py place_bracket: answered, no order
    "order rejected (no orderId returned)",                         # tradovate.py place_order: answered, no order
    "a Stop Limit order needs both a limit price and a trigger",    # tradovate.py STOPLIMIT_INCOMPLETE: not sent
    "bracketed stop entries need a broker OSO",                     # base.py place_bracket (legged fallback): not sent
)
LAB_BAD_ORDER = "The Desk cannot check this order."
LAB_NO_STOP = "Every entry needs a stop held at the broker."
LAB_WRONG_SIDE = "The stop must sit on the losing side of the entry."
LAB_NOT_A_PAIR = "Only a buy-stop and sell-stop pair can be linked."
LAB_TOO_LATE = "Too late for a new trade today."
LAB_NOT_WRITTEN = "The Desk could not write this trade down. Nothing was sent."
# A refused entry whose words say the answer never came: the order may exist at the broker (broker/tradovate.py
# place_bracket: "incl. a timeout, where the OSO may exist"). Such a round is never clean.
LAB_UNKNOWN_WORDS = ("oso failed", "timeout", "timed out", "unreachable", "outcome unknown")


@dataclass
class LabLeg:
    """One entry of a Lab strategy, as the engine places it. Duck-types rules.Signal for _place_one."""
    iid: int                            # the strategy's own order id
    side: str                           # "Buy" | "Sell"
    entry: str                          # "Market" | "Stop" | "Limit"
    entry_price: Optional[float]
    sl_px: float
    tp_px: Optional[float]              # None = no target order
    tp_rr: Optional[float]
    ref_px: Optional[float]
    move: bool = False                  # move_brackets_to_fill


class LabMixin:
    """The Lab methods of the Engine (engine.py: class Engine(LabMixin))."""

    def _archived(self, st: DayState) -> bool:
        """A closed Lab round filed under "strategy@account#n". False for every state the plain key holds --
        so for every state of every other kind."""
        return self.states.get(f"{st.strategy}@{st.account}") is not st

    # --- the extras ---------------------------------------------------------------------------------
    def _lab_path(self):
        return self._root / f"labday-{self._today()}.json"

    def _lab_mem(self) -> dict:
        """{state key: extras}, read from today's file at the first Lab call. Never raises."""
        mem = self.__dict__.get("_lab")
        if mem is None:
            mem = {}
            try:
                p = self._lab_path()
                if p.exists():
                    data = json.loads(p.read_text())
                    if isinstance(data, dict):
                        mem = {str(k): v for k, v in data.items() if isinstance(v, dict)}
                        for k, v in mem.items():
                            self._lab_coerce(v, carried_key="#c" in k)
            except Exception as e:  # noqa: BLE001 -- lost extras mean "not clean", never a crash
                print(f"homebase engine: reading the Lab rounds file failed: {e!r}", file=sys.stderr)
            self._lab = mem
        return mem

    @staticmethod
    def _lab_coerce(x: dict, carried_key: bool = False) -> None:
        """A file is only text: every value the section leans on is given its type back, and a number must be
        finite. One that is wrong takes the safe value AND makes the round not clean (never an exception on every
        tick). The safe value of "this round's close was sent" is YES: a mark that does not read, that is not a
        time, or that is missing beside a closing reason / an unconfirmed marker / the older key (closing_ms)
        means a close MAY be out, and no second one is ever sent."""
        inf = float("inf")

        def num(v) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != inf

        def whole(v) -> bool:
            return isinstance(v, int) and not isinstance(v, bool)

        bad = False
        if any(k not in x for k in ("round", "iid", "legs", "cancelled", "clean", "closing", "placed_ms")):
            # not a round's extras at all (every build wrote these keys): this trade's record is LOST (hands off)
            x["lost"], bad = True, True
        for k, typ in (("cancelled", list), ("legs", dict), ("iid", dict)):
            if k in x and not isinstance(x[k], typ):
                x[k], bad = typ(), True
        if any(v not in ("Buy", "Sell") for v in x.get("cancelled") or []):
            x["cancelled"], bad = [v for v in x["cancelled"] if v in ("Buy", "Sell")], True
        # O-1: what a file says was cancelled is a hint. `cancelled` holds only what THIS process read at the
        # broker; every path that skips an "already cancelled" entry therefore asks the broker again after a start
        hint = x.get("cancelled_hint") if isinstance(x.get("cancelled_hint"), list) else []
        x["cancelled_hint"] = sorted({v for v in list(x.get("cancelled") or []) + hint if v in ("Buy", "Sell")})
        x["cancelled"] = []
        if any(not isinstance(v, dict) for v in (x.get("legs") or {}).values()):
            x["legs"], bad = {k: v for k, v in x["legs"].items() if isinstance(v, dict)}, True
        for leg in (x.get("legs") or {}).values():
            for k in ("entry_price", "sl_px", "tp_px", "tp_rr", "ref_px"):
                if leg.get(k) is not None and not num(leg[k]):
                    leg[k], bad = None, True
            if "move" in leg and not isinstance(leg["move"], bool):
                leg["move"], bad = False, True
        if any(not whole(v) for v in (x.get("iid") or {}).values()):
            x["iid"], bad = {k: v for k, v in x["iid"].items() if whole(v)}, True
        if "round" in x and not whole(x["round"]):
            x["round"], bad = None, True
        for k in ("placed_ms", "entry_ms", "exit_ms"):
            if x.get(k) is not None and not num(x[k]):
                x[k], bad = None, True
        for k in ("clean", "check", "unconfirmed", "close_ok", "blind", "move", "lost", "lost_said"):
            if k in x and not isinstance(x[k], bool):
                x[k], bad = k not in ("clean", "move", "lost_said"), True
        if "net_bad" in x and not (whole(x["net_bad"]) and x["net_bad"] >= 0):
            x["net_bad"], bad = 0, True
        if x.get("net_bad_ms") is not None and not num(x["net_bad_ms"]):
            x["net_bad_ms"], bad = None, True
        if "closing_ms" in x:                        # the key of the first build of this section
            old = x.pop("closing_ms")
            if x.get("close_sent_ms") is None:
                x["close_sent_ms"] = old
        if x.get("closing") is not None and not isinstance(x["closing"], str):
            x["closing"] = str(x["closing"])
        sent = x.get("close_sent_ms")
        hint = bool(x.get("closing") or x.get("unconfirmed") or x.get("close_ok") or x.get("close_id"))
        if num(sent) and sent > 0:
            pass
        elif hint or (sent is not None and not (num(sent) and sent <= 0)):
            x["close_sent_ms"], bad = 1, True        # it may have been sent: never a second one
            if not x.get("close_ok"):
                x["unconfirmed"] = True
        elif sent is not None:
            x["close_sent_ms"], bad = None, True     # a zero with nothing that says a close was ever asked for
        if x.get("gone_ms") is not None and not (num(x["gone_ms"]) and x["gone_ms"] > 0):
            x["gone_ms"], bad = 1, True
        if x.get("carry") is not None and not isinstance(x["carry"], dict):
            # under a block's own key it stays a block; on a round of today it is no block (the round is its own)
            x["carry"], bad = ({"date": None, "status": None, "orders": []} if carried_key else None), True
        elif isinstance(x.get("carry"), dict):
            c = x["carry"]
            if not (isinstance(c.get("orders"), list) and all(isinstance(i, str) for i in c["orders"])):
                c["orders"] = [i for i in c["orders"] if isinstance(i, str)] if isinstance(c.get("orders"), list) else []
                c["unread"], bad = True, True        # its orders cannot all be named: cleared by hand only
            for k in ("sides", "was"):
                if not isinstance(c.get(k), dict):
                    c[k] = {}
            if c.get("filled") is not None and not isinstance(c["filled"], list):
                c["filled"] = None
            if not isinstance(c.get("date"), str):
                c["date"], c["unread"], bad = None, True, True
        if x.get("why") is not None and not isinstance(x["why"], str):
            x["why"] = None
        if x.get("close_id") is not None and not isinstance(x["close_id"], str):
            x["close_id"] = str(x["close_id"])
        if bad:
            x["check"], x["clean"], x["why"] = True, False, LAB_CANNOT_CHECK

    def _lab_save(self, strict: bool = False) -> None:
        """Write the extras whole (a temp file, then a rename). strict: raise when it cannot be written (a new
        round must be on disk before its order leaves); otherwise say so on stderr and go on."""
        try:
            p = self._lab_path()
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(self._lab_mem(), indent=2) + "\n")
            tmp.replace(p)
        except Exception as e:  # noqa: BLE001
            if strict:
                raise
            print(f"homebase engine: writing the Lab rounds file failed: {e!r}", file=sys.stderr)

    def _lab_ms(self) -> int:
        return int(self._now().timestamp() * 1000)

    def _lab_key(self, st: DayState) -> Optional[str]:
        key = f"{st.strategy}@{st.account}"
        if self.states.get(key) is st:
            return key
        return next((k for k, s in self.states.items() if s is st), None)

    @staticmethod
    def _lab_blank(n: int) -> dict:
        # close_sent_ms: THE fact that this round's one market-out was sent (written to disk before it leaves;
        # never judged by `closing`, which is only the reason text). close_ok / close_id: the broker accepted it.
        return {"round": n, "iid": {}, "legs": {}, "move": False, "closing": None, "close_sent_ms": None,
                "close_ok": False, "close_id": None, "gone_ms": None, "cancelled": [], "clean": False,
                "check": False, "unconfirmed": False, "blind": False, "carry": None,
                "lost": False, "lost_said": False, "net_bad": 0, "net_bad_ms": None,
                # sides a FILE said were cancelled: a hint, never a fact, until the broker is read (_lab_hints)
                "cancelled_hint": [],
                "placed_ms": None, "entry_ms": None, "exit_ms": None, "why": None}

    def _lab_round_no(self, st: DayState) -> int:
        """A round's number when its extras do not say: an archived one from its key, the open one after them."""
        key = self._lab_key(st) or ""
        tail = key.rsplit("#", 1)[-1] if "#" in key else ""
        if self._archived(st) and tail.isdigit():
            return int(tail)
        return 1 + sum(1 for s in self.states.values()
                       if s is not st and s.strategy == st.strategy and s.account == st.account
                       and s.date == st.date and self._archived(s))

    def _lab_x(self, st: DayState) -> dict:
        """The round's extras. A round that acted and has none (the file was lost) gets a blank set that can
        never be clean: its orders cannot be checked."""
        mem = self._lab_mem()
        key = self._lab_key(st)
        x = mem.get(key) if key is not None else None
        if x is None:
            x = self._lab_blank(self._lab_round_no(st))
            if st.status != "idle":
                x["check"], x["why"], x["lost"] = True, LAB_CANNOT_CHECK, True
            if key is not None:
                mem[key] = x
        for k, v in self._lab_blank(0).items():          # a file written by an older build: fill what it lacks
            if k not in x:
                x[k] = v
        if x.get("round") is None:
            x["round"] = self._lab_round_no(st)
        if x.get("lost") and not x.get("lost_said"):
            # This trade's record was lost (its extras are missing or do not read). The Desk stops owning what it
            # cannot account for: from here the Lab section sends nothing and cancels nothing for it, in any
            # status; it is never clean, and it is carried as a block at the day roll. Said once.
            x["lost_said"], x["check"], x["clean"], x["why"] = True, True, False, LAB_CANNOT_CHECK
            try:
                self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                             reason="this trade's record was lost: nothing is sent or cancelled for it by the "
                                    "strategy's own controls; the desk-wide Kill still works", actions=[])
                self._lab_save()
            except Exception as e:  # noqa: BLE001 -- never out of a read
                print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)
        return x

    def _lab_stamp(self, st: DayState, x: dict) -> bool:
        """When the entry and the exit were first seen here (there is no hook inside on_fill). True = changed."""
        changed = False
        if st.entry_side and not x.get("entry_ms"):
            x["entry_ms"], changed = self._lab_ms(), True
        if st.status in ("done", "error") and not x.get("exit_ms"):
            x["exit_ms"], changed = self._lab_ms(), True
        return changed

    def _lab_levels(self, st: DayState, x: dict) -> tuple:
        """(stop, target) of the round's trade: the state's own, else the filled leg's as it was sent."""
        leg = (x.get("legs") or {}).get(st.entry_side or "") or {}
        return (st.sl_px if st.sl_px is not None else leg.get("sl_px"),
                st.tp_px if st.tp_px is not None else leg.get("tp_px"))

    # --- hook 3: the brackets after the fill (the tester's law, backtest/engine.py _fill) ---------
    async def _lab_move(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> dict:
        """With `move` and a ref the stop shifts by fill - ref, and so does a target that has no RR; with an RR
        the target is fill +/- rr x |fill - stop| (the moved stop). Only an order whose price changed by half a
        tick or more, and whose id is known, is modified. st.sl_px / st.tp_px end as the levels that REST at the
        broker. Never raises (on_fill journals what it returns as `brackets_moved`), and always returns both
        `sl` and `tp` (metrics reads them together)."""
        st.brackets_moved = True                  # once per trade
        out = {"fill": None, "sl": st.sl_px, "tp": st.tp_px, "moved": False}
        if self._archived(st):                    # a block carried from an earlier day: read only, always
            return {**out, "error": "a carried round: nothing is moved"}
        try:
            x = self._lab_x(st)
            if x.get("lost"):                     # hands off: its stop and target stay where the broker has them
                return {**out, "error": "this trade's record was lost: nothing is moved"}
            leg = (x.get("legs") or {}).get(st.entry_side or "") or {}
            sl0, tp0 = self._lab_levels(st, x)
            rr = leg.get("tp_rr") if leg else st.tp_rr
            st.sl_px, st.tp_px, st.tp_rr = sl0, tp0, rr
            out.update(sl=sl0, tp=tp0)
            if self._lab_stamp(st, x):
                self._lab_save()
            if st.entry_fill is None:
                self._save()
                return {**out, "error": "no fill price"}
            fill = float(st.entry_fill)
            out["fill"] = round(fill, 6)
            sign = 1 if st.entry_side == "Buy" else -1
            tick = tick_size(cfg.symbol) or 0.25
            sl, tp = sl0, tp0
            if leg.get("move") and leg.get("ref_px") is not None:
                d = fill - float(leg["ref_px"])
                sl = None if sl is None else _to_tick(sl + d, tick)
                if rr is None:
                    tp = None if tp is None else _to_tick(tp + d, tick)
            if rr is not None and sl is not None:
                tp = _to_tick(fill + sign * float(rr) * abs(fill - sl), tick)
            sl_id, tp_id = ((st.up_sl_id, st.up_tp_id) if st.entry_side == "Buy"
                            else (st.dn_sl_id, st.dn_tp_id))
            jobs, errs = [], []
            for name, new, old, oid in (("sl", sl, sl0, sl_id), ("tp", tp, tp0, tp_id)):
                if new is None or (old is not None and abs(new - old) < tick / 2):
                    continue
                if not oid:
                    errs.append(f"{name}: order id unknown")
                    continue
                jobs.append((name, new, ad.modify_order(oid, "Stop", stop_price=new, qty=st.qty) if name == "sl"
                             else ad.modify_order(oid, "Limit", price=new, qty=st.qty)))
            if not jobs and not errs:
                self._save()
                return {**out, "moved": "not needed — levels unchanged"}
            res = await asyncio.gather(*(j[2] for j in jobs), return_exceptions=True)
            for (name, new, _), r in zip(jobs, res):
                if not isinstance(r, Exception) and r.ok:
                    setattr(st, f"{name}_px", new)
                else:
                    errs.append(f"{name}: {r if isinstance(r, Exception) else r.error}")
            self._save()
            return {**out, "sl": st.sl_px, "tp": st.tp_px, "moved": not errs,
                    **({"error": "; ".join(errs)} if errs else {})}
        except Exception as e:  # noqa: BLE001 -- the fill is already in; the brackets rest where they were
            return {**out, "error": f"{type(e).__name__}: {e}"[:200]}

    # --- hook 4: why the trade ended ------------------------------------------------------------------
    def _lab_grade(self, st: DayState, px: Optional[float]) -> str:
        """The reason the round is being closed for (a flatten) when there is one; else "sl" or "tp" by the
        nearer level that exists; else "exit". Never raises: it runs inside on_fill."""
        try:
            x = self._lab_x(st)
            if not x.get("exit_ms"):
                x["exit_ms"] = self._lab_ms()
            self._lab_save()                      # an unconfirmed close stays unconfirmed: only the settle, with
                                                  # the orders AND the net read, may call this round clean
            if x.get("close_sent_ms") and x.get("closing"):
                return str(x["closing"])          # (a close that only MAY be out has no reason: graded by level)
            sl, tp = self._lab_levels(st, x)
            if px is None or (sl is None and tp is None):
                return "exit"
            if sl is None or tp is None:
                return "sl" if tp is None else "tp"
            return "tp" if abs(px - tp) <= abs(px - sl) else "sl"
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: grading a Lab exit failed: {e!r}", file=sys.stderr)
            return "exit"

    # --- the rounds: what the Desk reads -----------------------------------------------------------
    def _lab_roll(self) -> None:
        """The first Lab call of a day, and the first after a start: yesterday's Lab rounds leave the day. One
        that is NOT resolved (placing / placed / live, or its orders never read ended) is carried as a block
        for its (strategy, account): see _lab_carry. Never raises."""
        today = self._today()
        names = frozenset(n for n, c in self.cfg.strategies.items()
                          if isinstance(n, str) and getattr(c, "kind", None) == LAB)
        seen = self.__dict__.get("_lab_names")
        if self.__dict__.get("_lab_day") == today and seen is not None and names <= seen:
            return
        # N-1: a Lab strategy that was not in the config at the roll (its record did not read at that moment)
        # was left completely alone. When it is there again, the roll runs once more, for it only.
        only = None if self.__dict__.get("_lab_day") != today or seen is None else names - seen
        self._lab_day, self._lab_names = today, (names if only is None else seen | names)
        try:
            self._lab_roll_day(today, only)
        except Exception as e:  # noqa: BLE001 -- the position read in front of every entry still stands
            print(f"homebase engine: the Lab day roll failed: {e!r}", file=sys.stderr)

    @staticmethod
    def _lab_unresolved(rec: dict, x) -> bool:
        """A round (its state as a dict, its extras) that an account may not trade past."""
        if isinstance(x, dict) and isinstance(x.get("carry"), dict):
            return True                               # a block that never cleared
        status = rec.get("status")
        if status in ("placing", "placed", "live"):
            return True
        if status in (None, "idle"):
            return False
        return not (isinstance(x, dict) and x.get("clean") is True and not x.get("check")
                    and not x.get("unconfirmed"))

    def _lab_last_files(self, today: str) -> tuple:
        """(date, extras, states) of the most recent earlier day that has a Lab file, at most 7 days back. A file
        that is missing or does not read carries nothing: (None, {}, {})."""
        try:
            now, best = dt.date.fromisoformat(today), None
            for f in self._root.glob("labday-*.json"):
                try:
                    d = dt.date.fromisoformat(f.name[len("labday-"):-len(".json")])
                except ValueError:
                    continue
                if d < now and (now - d).days <= 7 and (best is None or d > best):
                    best = d
            if best is None:
                return None, {}, {}
            lab = json.loads((self._root / f"labday-{best.isoformat()}.json").read_text())
            day = json.loads(self._day_path(best.isoformat()).read_text())
            if not isinstance(lab, dict) or not isinstance(day, dict):
                return None, {}, {}
            return best.isoformat(), lab, day
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: an earlier day's Lab files do not read: {e!r}", file=sys.stderr)
            return None, {}, {}

    @staticmethod
    def _lab_rec_ok(rec) -> bool:
        """A day state as a file gives it (a dict): every field the Lab section -- or on_fill -- would lean on has
        its type and a sane value. A quantity below zero once divided by zero inside on_fill."""
        inf = float("inf")

        def num(v) -> bool:
            return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != inf)

        def count(v) -> bool:
            return isinstance(v, int) and not isinstance(v, bool) and v >= 0

        return (isinstance(rec, dict) and isinstance(rec.get("strategy"), str) and isinstance(rec.get("account"), str)
                and isinstance(rec.get("date"), str)
                and rec.get("status") in ("idle", "placing", "placed", "live", "done", "error")
                and all(rec.get(k) is None or isinstance(rec[k], str) for k in ("exit_reason", "note", "take_src"))
                and count(rec.get("qty")) and count(rec.get("entry_qty", 0)) and count(rec.get("exit_qty", 0))
                and rec.get("entry_side") in (None, "Buy", "Sell")
                and all(rec.get(k) is None or isinstance(rec[k], str) for k in LAB_ID_FIELDS)
                # every number on_fill, _close_if_out, _gross_pnl, _fee and _set_take_px do arithmetic on, for any
                # kind: the levels fields too (tp_pts makes _set_take_px compute a take price at the entry fill)
                and all(num(rec.get(k)) for k in ("entry_fill", "exit_fill", "entry_anchor", "sl_px", "tp_px", "tp_rr",
                                                  "upper_px", "lower_px", "pnl", "sl_pts", "sl_sell_pts", "tp_pts",
                                                  "take_usd", "take_px")))

    def _lab_roll_day(self, today: str, only=None) -> None:
        """`only`: None for the day's roll; else the names of Lab strategies that came (back) into the config
        after it -- the roll is run again for their states and rows alone.
        Whose is a key? By its strategy name in self.cfg, three ways (N-1):
          kind "lab"            the Lab section's: checked, carried, pruned;
          another kind          foreign: never looked at; extras a Lab file holds for it are dropped, said once;
          not in the config     nobody's just now: its state, its extras in memory and its entry in the Lab file
                                all stay exactly as they are, with no journal line, until the strategy is back."""
        mem = self._lab_mem()
        if only is None:
            first_today = not self._lab_path().exists()   # this day's file is written below: a later restart skips the disk
            if first_today:
                self._lab_disk_day = today
        else:                                         # a strategy that came back: the disk too, if this process read it
            first_today = self.__dict__.get("_lab_disk_day") == today
        found: dict = {}                              # (strategy, account) -> the round to carry
        unread: dict = {}                             # (strategy, account) -> a record that does not read

        def lab(name) -> bool:
            if not isinstance(name, str):            # O-3: a damaged name (a list, a number) is not a Lab strategy,
                return False                         # and is never used as a dict key here
            cfg = self.cfg.strategies.get(name)
            return cfg is not None and cfg.kind == LAB and (only is None or name in only)

        def foreign(name) -> bool:                   # in the config, and of another kind
            cfg = self.cfg.strategies.get(name) if isinstance(name, str) else None
            return cfg is not None and cfg.kind != LAB

        def strange(key) -> None:                    # extras a Lab file holds for another kind's state
            del mem[key]
            self.journal("lab_foreign_key", key=key, note="the Lab file named a state that is not a Lab strategy's")

        def pair_of(key) -> tuple:
            name, _, rest = str(key).partition("@")
            return name, rest.split("#", 1)[0]

        def blind(key, rec, date) -> None:
            """A row that does not read: carried all the same (fail closed), with whatever order ids it names."""
            pair = pair_of(key)
            if pair[0] and pair[1]:
                u = unread.setdefault(pair, {"date": date if isinstance(date, str) else today, "orders": []})
                if isinstance(rec, dict):
                    u["orders"] += [rec[k] for k in LAB_ID_FIELDS
                                    if isinstance(rec.get(k), str) and rec[k] and rec[k] not in u["orders"]]

        def take(key, rec, x, date) -> None:
            """One row of an earlier day, on its own; it never stops the rows of the other accounts."""
            pair = pair_of(key)
            try:
                x = x if isinstance(x, dict) else None
                if x is not None:
                    self._lab_coerce(x, carried_key="#c" in str(key))
                if not self._lab_rec_ok(rec) or (rec["strategy"], rec["account"]) != pair:
                    raise ValueError("a field is missing or of the wrong type")
                if rec["status"] == "idle" and x is not None and (x.get("iid") or x.get("legs") or x.get("carry")):
                    raise ValueError("an idle state beside a round's extras")
                if not self._lab_unresolved(rec, x):
                    return
                was = x.get("carry") if x is not None and isinstance(x.get("carry"), dict) else None
                if was is not None and was.get("unread"):
                    u = unread.setdefault(pair, {"date": was.get("date") or date, "orders": []})
                    u["orders"] += [i for i in was.get("orders") or [] if i not in u["orders"]]
                    return
                c = found.setdefault(pair, {
                    "date": (was or {}).get("date") or date, "status": (was or {}).get("status") or rec["status"],
                    "round": (x or {}).get("round"), "iid": (x or {}).get("iid"), "placed_ms": (x or {}).get("placed_ms"),
                    "orders": [], "sides": {}, "filled": (was or {}).get("filled"), "was": dict((was or {}).get("was") or {})})
                if was is not None:
                    c["orders"] += [i for i in was.get("orders") or [] if i not in c["orders"]]
                    c["sides"].update(was.get("sides") or {})
                    return
                for k, side in (("upper_id", "Buy"), ("lower_id", "Sell"), ("up_sl_id", "Sell"), ("up_tp_id", "Sell"),
                                ("dn_sl_id", "Buy"), ("dn_tp_id", "Buy")):
                    if rec.get(k) and rec[k] not in c["orders"]:
                        c["orders"].append(rec[k])
                        c["sides"][rec[k]] = side
                if not c["was"] or rec.get("entry_side"):         # what was known of the trade, for the owner
                    leg = ((x or {}).get("legs") or {}).get(rec.get("entry_side") or "") or {}
                    c["was"] = {"status": rec["status"], "entry_side": rec.get("entry_side"), "qty": rec.get("qty"),
                                "entry_qty": rec.get("entry_qty", 0), "entry_fill": rec.get("entry_fill"),
                                "exit_qty": rec.get("exit_qty", 0), "exit_fill": rec.get("exit_fill"),
                                "sl": rec.get("sl_px") if rec.get("sl_px") is not None else leg.get("sl_px"),
                                "tp": rec.get("tp_px") if rec.get("tp_px") is not None else leg.get("tp_px")}
            except Exception as e:  # noqa: BLE001
                blind(key, rec, date)
                print(f"homebase engine: a Lab record of {date} does not read ({key}): {e!r}", file=sys.stderr)

        changed = False
        for k, st in list(self.states.items()):
            pair = pair_of(k)
            if not lab(pair[0]):
                # O-2: the Lab section never looks at, changes or deletes a state of another kind, whatever a
                # labday file names. A state is the Lab section's by its KEY (what _state built it under).
                # N-1: and a name that is in NO config is left completely alone, its extras too
                if k in mem and foreign(pair[0]):
                    strange(k)
                continue
            if st.date != today and isinstance(st.date, str):    # 1. what this engine still holds of an earlier day
                take(k, asdict(st), mem.get(k), st.date)
            elif st.date == today and (self._lab_carried(st) or (
                    self._lab_rec_ok(asdict(st)) and (st.strategy, st.account) == pair)):
                continue
            else:                                     # G1: a state of TODAY whose fields do not read (a damaged
                blind(k, asdict(st), today)           # day file): out of on_fill's way, a block from here on
            del self.states[k]
            changed = True
        for k in [k for k in mem if k not in self.states]:
            name = pair_of(k)[0]
            if lab(name):                             # a Lab strategy's extras with no state: gone with the day
                del mem[k]
            elif foreign(name):
                strange(k)                            # (a name in no config: left as it is)
        if first_today:                               # 2. what the files of the last Lab day say (a restart)
            date, lab_old, day_old = self._lab_last_files(today)
            for k, rec in day_old.items():
                pair = pair_of(k)
                if not lab(pair[0]) or pair in unread:
                    continue                          # (O-2: never a row of another kind)
                d = rec.get("date") if isinstance(rec, dict) else None
                if d != date:
                    try:
                        older = isinstance(d, str) and dt.date.fromisoformat(d) < dt.date.fromisoformat(date)
                    except ValueError:
                        older = False
                    if k in lab_old or not older:     # M3: not a state of a day before: a row that does not read
                        blind(k, rec, date)
                    continue
                take(k, rec, lab_old.get(k), date)
        for pair in list(found):
            if pair in unread:                        # one row of the pair did not read: the whole pair is unread
                u = unread[pair]
                u["orders"] += [i for i in found.pop(pair)["orders"] if i not in u["orders"]]
        for pair, c in found.items():                 # 3. a block per pair, as a state of today under its own key
            try:
                changed = self._lab_carry_make(pair, c, today) or changed
            except Exception as e:  # noqa: BLE001 -- this row does not read after all: carried unread
                unread.setdefault(pair, {"date": c.get("date"), "orders": list(c.get("orders") or [])})
                print(f"homebase engine: a Lab round of {c.get('date')} could not be carried as it is: {e!r}",
                      file=sys.stderr)
        for pair, u in unread.items():
            changed = self._lab_carry_make(pair, {"date": u["date"] if isinstance(u["date"], str) else today,
                                                  "status": None, "orders": u["orders"], "unread": True}, today) or changed
        if only is None:
            self.__dict__.pop("_lab_tries", None)     # G2: a new day reads on the fast schedule again
        if changed:
            self._save()
        self._lab_save()                              # always: the file says "this day was rolled"

    def _lab_carry_make(self, pair: tuple, c: dict, today: str) -> bool:
        """One carried block: a state of today under "strategy@account#c<date>", and NOTHING but a block. Its
        status is `error` (never live, placed or placing), it holds no order id and no entry fact, so no path of
        the engine, the chart's bot lock, reconcile_account or check_takes sees a busy bot or a position in it,
        and on_fill can book no fill to it. What was known of the trade (side, size, entry fill, its order ids,
        its day) is kept in the extras for the owner. A block whose record did not read (`unread`) clears by
        hand only."""
        name, account = pair
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB or any(
                self._lab_carried(s) for s in self.states.values()
                if s.strategy == name and s.account == account and s.date == today):
            return False
        key = f"{name}@{account}#c{c['date']}"
        while key in self.states:
            key += "+"
        why = LAB_BAD_RECORD if c.get("unread") else LAB_CANNOT_CHECK
        was = c.get("was") if isinstance(c.get("was"), dict) else {}
        qty = was.get("qty")
        st = DayState(strategy=name, account=account, date=today,
                      qty=qty if isinstance(qty, int) and not isinstance(qty, bool) and qty >= 0 else 0,
                      status="error", exit_reason="carried", note=why)
        n = c.get("round")
        n = n if isinstance(n, int) and not isinstance(n, bool) else 1
        x = self._lab_blank(n)
        x.update(check=True, clean=False, why=why, iid=c["iid"] if isinstance(c.get("iid"), dict) else {},
                 placed_ms=c.get("placed_ms"),
                 carry={"date": c["date"], "status": c.get("status"), "since_ms": self._lab_ms(),
                        "orders": [i for i in c.get("orders") or [] if isinstance(i, str)],
                        "sides": dict(c.get("sides") or {}), "was": dict(was),
                        "filled": c["filled"] if isinstance(c.get("filled"), list) else None,
                        "unread": bool(c.get("unread"))})
        self._lab_coerce(x, carried_key=True)
        x["why"] = why
        self.states[key] = st
        self._lab_mem()[key] = x
        self.journal("lab_carry", strategy=name, account=account, round=n, date=c["date"], status=c.get("status"),
                     orders=x["carry"]["orders"], **({"unread": True} if c.get("unread") else {}))
        return True

    def _lab_carried(self, st: DayState) -> bool:
        """A block carried from an earlier day: a state of today that only says "this account is not resolved"."""
        x = self._lab_mem().get(self._lab_key(st) or "")
        return isinstance(x, dict) and isinstance(x.get("carry"), dict)

    async def _lab_carry_check(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict) -> None:
        """Read only, never an order. An order of the block that newly reads Filled is written down
        (`lab_carry_fill`) and changes nothing. The block clears when every known order reads ended at the broker
        AND the account's net in the market reads zero. Every 5 s for a minute, then every 30 s. A block whose
        record did not read is cleared by hand only."""
        key = self._lab_key(st)
        tries = self.__dict__.setdefault("_lab_tries", {})
        rk = f"carry:{key}"
        gap = LAB_FLAT_RETRY_S if tries.get(rk, 0) < 12 else LAB_CHECK_RETRY_S
        carry = x["carry"]
        if key is None or not ad.connected or carry.get("unread") \
                or time.time() - self._retry_at.get(rk, 0.0) < gap:
            return
        self._retry_at[rk] = time.time()
        tries[rk] = tries.get(rk, 0) + 1
        orders = [i for i in carry.get("orders") or [] if isinstance(i, str)]
        status: dict = {}
        for i in orders:
            try:
                status[i] = await ad.get_order_status(i)
            except Exception:  # noqa: BLE001 -- unread: asked again
                status[i] = None
        if self.states.get(key) is not st:
            return
        filled = [i for i in orders if status[i] == "Filled"]
        if not isinstance(carry.get("filled"), list):
            carry["filled"] = filled                  # the first read: what had filled before anyone looked
            self._lab_save()
        else:
            for i in [i for i in filled if i not in carry["filled"]]:
                try:
                    qty = (await ad.get_order_state(i) or {}).get("filled_qty")
                except Exception:  # noqa: BLE001
                    qty = None
                carry["filled"].append(i)
                self._lab_save()
                self.journal("lab_carry_fill", strategy=st.strategy, account=st.account, round=x.get("round"),
                             date=carry.get("date"), order_id=i, side=(carry.get("sides") or {}).get(i), qty=qty,
                             price=None, seen="the order's status at the broker")
        if any(status[i] not in TERMINAL for i in orders):
            return
        try:
            net = await ad.get_net_position(cfg.symbol)
        except Exception:  # noqa: BLE001 -- unreadable is NOT flat
            return
        if net is None or isinstance(net, bool) or int(net) != 0 or self.states.get(key) is not st:
            return
        del self.states[key]
        self._lab_mem().pop(key, None)
        tries.pop(rk, None)
        self._save()
        self._lab_save()
        self.journal("lab_carry_cleared", strategy=st.strategy, account=st.account, round=x.get("round"),
                     date=carry.get("date"))

    async def lab_clear_block(self, name: str, account: str) -> dict:
        """The owner's explicit "this account is fine": remove the block carried for (strategy, account). Only when
        the account's net in the strategy's market reads exactly 0 AND none of the block's known orders reads
        working or pending (one that cannot be read does not stop it: that is what the by-hand clear is for). A
        position, a read that fails or a working old order: refused with the sentence, nothing changes. It sends
        nothing and cancels nothing.
        -> {"ok": True, "cleared": [dates]} | {"ok": False, "reason": sentence[, "orders": [the working ones]]}"""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return {"ok": False, "reason": LAB_NOT_ON_DESK}
        self._lab_roll()

        def blocks() -> list:
            return [(k, s) for k, s in self.states.items() if s.strategy == name and s.account == account
                    and s.date == self._today() and self._lab_carried(s)]

        if not blocks():
            return {"ok": False, "reason": LAB_NO_BLOCK}
        why = await self._lab_position(name, cfg, account, said=False)
        if why is not None:
            return {"ok": False, "reason": why}
        ad = self.adapters.get(account)
        working = []
        for k, st in blocks():
            for i in (self._lab_x(st).get("carry") or {}).get("orders") or []:
                try:
                    status = await ad.get_order_status(i)
                except Exception:  # noqa: BLE001 -- an order that does not read does not stop a clear by hand
                    status = None
                if status is not None and status not in TERMINAL and i not in working:
                    working.append(i)            # any status that reads and is not ended: it could still fill
        if working:                                  # it could still fill, into a trade that is not this one's
            return {"ok": False, "reason": LAB_OLD_ORDER_WORKING, "orders": sorted(working)}
        cleared = []
        for k, st in blocks():                       # read again: the reads yielded
            x = self._lab_mem().pop(k, None) or {}
            del self.states[k]
            self.__dict__.get("_lab_tries", {}).pop(f"carry:{k}", None)
            date = (x.get("carry") or {}).get("date")
            cleared.append(date)
            self.journal("lab_carry_cleared", strategy=name, account=account, round=x.get("round"), date=date,
                         why="by hand")
        if cleared:
            self._save()
            self._lab_save()
        return {"ok": True, "cleared": cleared} if cleared else {"ok": False, "reason": LAB_NO_BLOCK}

    def _lab_mark_check(self, st: DayState, x: dict, reason: str, *, why: Optional[str] = None,
                        actions: Optional[list] = None, detail: Optional[str] = None) -> None:
        """This round's orders cannot be checked: it is never clean today, so the account takes no new Lab trade.
        Journaled once (`lab_check`)."""
        if x.get("check"):
            return
        x["check"], x["clean"], x["why"] = True, False, why or LAB_CANNOT_CHECK
        self._lab_save()
        try:
            self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                         reason=reason, actions=actions or [], **({"detail": detail} if detail else {}))
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)

    def _lab_stuck(self, st: DayState, x: dict) -> bool:
        """A round that can never be clean: its extras were lost, its placement outcome is unknown, both of its
        entries filled, or a kill's market-out reported failure."""
        if not x.get("check"):
            if st.note == PLACING_UNKNOWN:
                self._lab_mark_check(st, x, PLACING_UNKNOWN)
            elif st.status == "error" and st.exit_reason == "both_filled":
                self._lab_mark_check(st, x, "both entries filled")
            elif st.note == MARKET_OUT_FAILED:
                self._lab_mark_check(st, x, MARKET_OUT_FAILED)
            elif x.get("blind"):                     # a stop order the Desk does not know: never clean
                self._lab_mark_check(st, x, "the Desk does not know this trade's stop order", why=LAB_NO_STOP_ID)
        return bool(x.get("check"))

    def _lab_clean(self, st: DayState) -> bool:
        """I-2: may a new round follow this one? Idle: yes. Otherwise only once it is over and its orders were
        read terminal (a `clean` mark on a round that is not over is not believed)."""
        if st.status == "idle":
            return True
        x = self._lab_x(st)
        if self._lab_stuck(st, x) or x.get("unconfirmed"):
            return False
        return bool(x.get("clean")) and st.status in ("done", "error")

    def lab_rounds(self, name: str) -> list[dict]:
        """Today's rounds of a Lab strategy, oldest first: one row per round per account; a block carried from an
        earlier day is a row too (`carried`, with its own `date`). No broker call. It is not memory only: the
        first call of a day runs the day roll (it may read the last Lab day's two files, and writes today's), and
        an entry or exit time seen here for the first time is written to the Lab file."""
        out = []
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:           # never extras for a strategy of another kind
            return out
        self._lab_roll()
        for st in self.day_states(name):
            if st.status == "idle":
                continue
            x = self._lab_x(st)
            if self._lab_stamp(st, x):
                self._lab_save()
            sl, tp = self._lab_levels(st, x)
            carry = x.get("carry") if isinstance(x.get("carry"), dict) else None
            out.append({"account": st.account, "round": x.get("round"), "status": st.status,
                        "date": (carry or {}).get("date") or st.date, "carried": carry is not None,
                        "iid": dict(x.get("iid") or {}), "qty": st.qty, "entry_side": st.entry_side,
                        # an entry adopted from an order read (_guard_placed: its fill push was missed) has a side
                        # and no counted fill: it went in whole, as _close_if_out counts it
                        "entry_qty": st.qty if st.entry_side and not st.entry_qty else st.entry_qty,
                        "entry_fill": st.entry_fill, "exit_qty": st.exit_qty,
                        "exit_fill": st.exit_fill, "exit_reason": st.exit_reason, "sl": sl, "tp": tp,
                        "pnl": st.pnl, "clean": self._lab_clean(st), "entry_ms": x.get("entry_ms"),
                        "exit_ms": x.get("exit_ms"), "why": x.get("why") or (st.note or None if st.status == "error" else None),
                        "cancelled": list(x.get("cancelled") or []), "closing": x.get("closing"),
                        "placed_ms": x.get("placed_ms"),
                        "orders": [i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id,
                                               st.dn_tp_id) if i]})
            if carry is not None:                    # a block: what was known of the trade when it was carried
                was = carry.get("was") if isinstance(carry.get("was"), dict) else {}
                out[-1].update(entry_side=was.get("entry_side"), qty=was.get("qty", st.qty),
                               entry_qty=was.get("entry_qty", 0), entry_fill=was.get("entry_fill"),
                               exit_qty=was.get("exit_qty", 0), exit_fill=was.get("exit_fill"),
                               sl=was.get("sl"), tp=was.get("tp"), orders=list(carry.get("orders") or []))
        out.sort(key=lambda r: (r["placed_ms"] or 0, r["round"] or 0, r["account"]))
        return out

    def lab_open(self, name: str) -> list[str]:
        """Accounts with a round of this strategy that is placing, placed or live, or whose orders are not checked
        (a block carried from an earlier day is one)."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return []
        self._lab_roll()
        return sorted({st.account for st in self.day_states(name)
                       if st.status in ("placing", "placed", "live") or not self._lab_clean(st)})

    # --- lab_enter ------------------------------------------------------------------------------------
    @staticmethod
    def _lab_num(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")

    def _lab_bad_legs(self, legs) -> Optional[str]:
        """The sentence for a set of legs the engine will not place; None when it will. One entry (market, stop or
        limit), or one buy stop and one sell stop; every entry with a stop on its losing side."""
        if not isinstance(legs, (list, tuple)) or not 1 <= len(legs) <= 2:
            return LAB_BAD_ORDER
        num = self._lab_num
        for g in legs:
            if not isinstance(g, LabLeg) or not isinstance(g.move, bool):
                return LAB_BAD_ORDER
            if not isinstance(g.iid, int) or isinstance(g.iid, bool) or g.side not in ("Buy", "Sell") \
                    or g.entry not in ("Market", "Stop", "Limit"):
                return LAB_BAD_ORDER
            if g.entry in ("Stop", "Limit") and not (num(g.entry_price) and g.entry_price > 0):
                return LAB_BAD_ORDER
            if g.entry == "Market" and g.entry_price is not None:
                return LAB_BAD_ORDER
            if not (num(g.sl_px) and g.sl_px > 0):
                return LAB_NO_STOP
            if (g.tp_px is not None and not num(g.tp_px)) or (g.ref_px is not None and not num(g.ref_px)) \
                    or (g.tp_rr is not None and not (num(g.tp_rr) and g.tp_rr > 0)):
                return LAB_BAD_ORDER
            if g.tp_rr is not None and g.tp_px is None:      # the first target is sent priced; the fill re-prices it
                return LAB_BAD_ORDER
            sign = 1 if g.side == "Buy" else -1
            base = g.ref_px if g.ref_px is not None else g.entry_price
            if base is not None:
                if not sign * (base - g.sl_px) > 0:
                    return LAB_WRONG_SIDE
                if g.tp_px is not None and not sign * (g.tp_px - base) > 0:
                    return LAB_BAD_ORDER
        if len(legs) == 2:
            a, b = legs
            if {a.side, b.side} != {"Buy", "Sell"} or a.entry != "Stop" or b.entry != "Stop" or a.iid == b.iid:
                return LAB_NOT_A_PAIR
            buy, sell = (a, b) if a.side == "Buy" else (b, a)
            if not buy.entry_price > sell.entry_price:
                return LAB_BAD_ORDER
        return None

    @staticmethod
    def _lab_clear_reject(err) -> bool:
        """Did the broker (or the adapter, before sending) clearly refuse this entry? Only the adapters' own fixed
        phrases count. Anything else -- no words, None, an exception's text, a phrase nobody listed -- is
        OUTCOME UNKNOWN: the order may exist at the broker under an id nobody recorded."""
        e = str(err if err is not None else "").strip()
        return e in LAB_CLEAR_REJECTS and not any(w in e.lower() for w in LAB_UNKNOWN_WORDS)

    @staticmethod
    def _same_market(a, b) -> bool:
        """The engine's own substring rule (on_fill's exit match): NQ also claims MNQ."""
        a, b = str(a or "").upper(), str(b or "").upper()
        return bool(a and b and (a in b or b in a))

    def _slot_busy(self, name: str, cfg: StrategyCfg, account: str, lab_only: bool = False) -> bool:
        """STRATEGIES THAT SHARE A MARKET on one broker account trade one at a time, first come -- a Lab strategy next
        to a Lab strategy, or next to a built-in (nq930, gc_nfp, a rule, a levels strategy), whatever the contract.
        True while another strategy has, today and on that broker account, a round that is placing, placed or live;
        one that went in and was never SEEN out (a Kill books a round done when its market order leaves: the fill that
        follows must not meet another strategy's round); and, for a Lab round, one that is over with its orders not
        read terminal (a block carried from an earlier day is one). on_fill books an opposite fill in a market as
        the live round's exit (by symbol and side, never by order id), so two rounds of one market are never open
        on an account together. A Lab round whose strategy is no longer in the config (its record did not load) is
        nobody's to judge: it holds too. `lab_only`: only a Lab round counts (a built-in strategy asking: two built-ins
        in one market keep sharing an account as they always did)."""
        today = self._today()

        def broker(a: str):
            return getattr(self.adapters.get(a), "broker_key", a)

        for s in self.states.values():
            if s.strategy == name or s.date != today or s.status == "idle" or broker(s.account) != broker(account):
                continue
            so = self.cfg.strategies.get(s.strategy)
            if so is None:
                if not s.strategy.startswith(LAB_PREFIX):
                    continue
            elif not self._same_market(so.symbol, cfg.symbol) or (lab_only and so.kind != LAB):
                continue
            went_in = (s.entry_qty or s.qty or 0) if s.entry_side else 0
            lab = s.strategy.startswith(LAB_PREFIX)
            if s.status in ("placing", "placed", "live") or (lab and not self._lab_clean(s)) \
                    or (s.exit_qty or 0) < went_in:
                return True
        return False

    def _lab_archive(self, key: str, st: DayState) -> None:
        """A terminal, clean round leaves the plain key (I-3: the next state made for the pair is inserted last)."""
        mem = self._lab_mem()
        x = mem.pop(key, None)
        n = int((x or {}).get("round") or self._lab_round_no(st))
        new = f"{key}#{n}"
        while new in self.states:                     # never write over a round
            n += 1
            new = f"{key}#{n}"
        del self.states[key]
        self.states[new] = st
        if x is not None:
            mem[new] = x

    def _lab_sits_out(self, name: str, cfg: StrategyCfg, account: str, qty, max_rounds: int) -> Optional[str]:
        """Steps 1-3 of lab_enter for one account, as one read with no side effect: the sentence when the account
        sits this trade out, None when a round may be opened. It is asked twice: before the position read (an
        account that sits out anyway costs no broker request) and again in the same run that opens the round."""
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1 or "#" in str(account) \
                or not any(a.get("account") == account for a in assignments(self.cfg, name)):
            return LAB_BAD_ORDER
        if self.account_locked(account):                                    # 1
            return LAB_ACCOUNT_STOPPED
        ad = self.adapters.get(account)
        if ad is None or not ad.connected:
            return LAB_NOT_CONNECTED
        rules = self.rules_for(account)
        if rules.day_take or rules.target_take:     # check_takes needs a price for every live state on the account
            return LAB_TAKE_RULE
        if self._slot_busy(name, cfg, account):                             # 2
            return LAB_SLOT_BUSY
        today = self._today()                                               # 3
        if any(self._archived(s) and (self._lab_carried(s) or not self._lab_clean(s))
               for s in self.day_states(name) if s.account == account):
            return LAB_CANNOT_CHECK                 # an earlier round (of today or of a day before) is not resolved
        cur = self.states.get(f"{name}@{account}")
        if cur is not None and cur.date == today and cur.status != "idle":
            if cur.status in ("placing", "placed", "live"):
                return LAB_ONE_AT_A_TIME
            if not self._lab_clean(cur):
                return LAB_CANNOT_CHECK
        n = 1 + max([int(self._lab_x(s).get("round") or 0) for s in self.day_states(name)
                     if s.account == account and s.status != "idle"], default=0)
        if n > max_rounds:
            return f"Daily limit reached ({max_rounds} trade{'' if max_rounds == 1 else 's'})."
        return None

    async def _lab_position(self, name: str, cfg: StrategyCfg, account: str, said: bool = True) -> Optional[str]:
        """Before EVERY Lab entry: the account's net in the strategy's market, read at the broker. Not zero, or
        not readable -> the sentence, and the account sits the trade out (it uses no round). A round of an
        earlier day that nobody carried, a position opened by hand, an order nobody recorded: none of them is
        traded on top of."""
        ad = self.adapters.get(account)
        try:
            net = await ad.get_net_position(cfg.symbol) if ad is not None and ad.connected else None
            net = None if net is None or isinstance(net, bool) else int(net)
        except Exception:  # noqa: BLE001 -- unreadable is NOT flat
            net = None
        why = LAB_NO_POSITION_READ if net is None else (
            f"The account already holds {cfg.symbol}. Check it." if net else None)
        if why is not None and said:
            self.journal("place_skipped", strategy=name, account=account, reason=why,
                         **({"net": net} if net is not None else {}))
        return why

    def _lab_may_enter(self, name: str) -> tuple:
        """Every strategy-level precondition of an entry, as one read with no side effect: (cfg | None, the
        sentence | None). Asked when lab_enter is called AND again, with no await in between, in the run that
        opens each account's round: a Kill, a disarm, the switch or the clock can move while the position is read."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return None, LAB_NOT_ON_DESK
        if not cfg.enabled:
            return cfg, LAB_OFF
        if self.killed_today(name):
            return cfg, LAB_KILLED
        now = self.now_et()
        hhmm = now.strftime("%H:%M")                 # the door's own rule, by the minute (labrun/door.py)
        if now.time() >= _hhmm(cfg.flat_et) or hhmm > cfg.accept_until_et or hhmm < cfg.accept_from_et:
            return cfg, LAB_TOO_LATE
        if not self.cfg.armed or cfg.shadow:
            return cfg, LAB_DISARMED
        return cfg, None

    def _lab_open_round(self, name: str, account: str, qty, legs: list, max_rounds: int, source: str) -> tuple:
        """Steps 0-4 of lab_enter for one account, in ONE run with no await: EVERY precondition (the strategy's
        and the account's), the archive of the last round and the new round written to disk can never be
        interleaved with another entry, a fill, a Kill or a disarm.
        -> (the new round's state | None, the answer, the strategy's cfg as it is now, the pair's requests | None)"""
        cfg, why = self._lab_may_enter(name)
        if why is None:
            why = self._lab_sits_out(name, cfg, account, qty, max_rounds)
        if why is not None:
            if why == LAB_DISARMED:                 # written down only, as the disarmed path of lab_enter does
                self.journal("shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run", strategy=name,
                             source=source, account=account, qty=qty, legs=[asdict(g) for g in legs])
            else:
                self.journal("place_skipped", strategy=name, account=account, reason=why)
            return None, {"ok": False, "round": None, "reason": why}, cfg, None
        key, today = f"{name}@{account}", self._today()
        cur = self.states.get(key)
        n = 1 + max([int(self._lab_x(s).get("round") or 0) for s in self.day_states(name)
                     if s.account == account and s.status != "idle"], default=0)
        x = self._lab_blank(n)                      # everything is built BEFORE anything changes: a failure here
        x["iid"] = {g.side: g.iid for g in legs}    # leaves no state behind, and never one that is "placing"
        x["legs"] = {g.side: asdict(g) for g in legs}
        x["move"] = any(g.move for g in legs)
        x["placed_ms"] = self._lab_ms()
        reqs = None
        if len(legs) == 2:
            pair = legs if legs[0].side == "Buy" else legs[::-1]
            reqs = tuple(OrderRequest(symbol=cfg.symbol, side=g.side, qty=qty, order_type=g.entry,
                                      price=g.entry_price, stop_price=g.sl_px, tp_price=g.tp_px,
                                      text="homebase:entry") for g in pair)
        if cur is not None and cur.date == today and cur.status != "idle":
            self._lab_archive(key, cur)
        else:
            self.states.pop(key, None)              # an idle or older state: the new one must be the pair's last
            self._lab_mem().pop(key, None)
        st = self._state(name, account)                                     # 4
        st.qty, st.status = qty, "placing"
        self._lab_mem()[key] = x
        self.__dict__.get("_lab_tries", {}).pop(key, None)   # the new round reads on the fast schedule again
        for k2 in (f"settle:{key}", f"flat:{key}", f"wait:{key}"):
            self.__dict__.get("_lab_said", {}).pop(k2, None)
            self._retry_at.pop(k2, None)
        try:                                        # durable BEFORE the order leaves
            self._save()
            self._lab_save(strict=True)
            self.journal("lab_round", strategy=name, account=account, round=n, qty=qty, source=source,
                         iid=x["iid"], legs=list(x["legs"].values()))
        except Exception as e:  # noqa: BLE001 -- nothing was sent
            st.status, st.exit_reason, st.note = "error", "error", f"not written: {e}"[:200]
            x["clean"] = True
            print(f"homebase engine: a Lab round could not be written: {e!r}", file=sys.stderr)
            try:                                    # M-D2: the day file may already say "placing": make it say
                self._save()                        # what memory says, or a restart sits the account out all day
            except Exception as e2:  # noqa: BLE001 -- best effort: it fails closed either way
                print(f"homebase engine: the day file could not follow: {e2!r}", file=sys.stderr)
            return None, {"ok": False, "round": n, "reason": LAB_NOT_WRITTEN}, cfg, None
        return st, {"ok": True, "round": n, "reason": None}, cfg, reqs

    async def _lab_enter_one(self, name: str, account: str, qty, legs: list, max_rounds: int, source: str,
                             t0: float) -> dict:
        cfg = self.cfg.strategies.get(name)
        why = LAB_NOT_ON_DESK if cfg is None or cfg.kind != LAB else \
            self._lab_sits_out(name, cfg, account, qty, max_rounds)
        if why is not None:
            self.journal("place_skipped", strategy=name, account=account, reason=why)
            return {"ok": False, "round": None, "reason": why}
        why = await self._lab_position(name, cfg, account)
        if why is not None:
            return {"ok": False, "round": None, "reason": why}
        # the read yielded: from here to the placement nothing awaits, and everything is asked again
        st, ans, cfg, reqs = self._lab_open_round(name, account, qty, legs, max_rounds, source)
        if st is None:
            return ans
        x = self._lab_x(st)
        try:                                                                # 5
            if reqs is None:
                got = await self._place_one(name, cfg, account, qty, legs[0], source, t0)
            else:
                got = await self._place(name, cfg, account, qty, reqs[0].price, reqs[1].price, source, t0,
                                        reqs=reqs)
        except Exception as e:  # noqa: BLE001 -- the outcome is unknown
            got = e
        words = ""                                  # the venue's own words for a failure (W1)
        if st.status == "placing":                                          # 6: never left as "placing"
            st.status, st.exit_reason = "error", "error"
            st.note = f"placement did not finish: {got}"[:200]
            words = (f"{type(got).__name__}: {got}" if isinstance(got, Exception) else str(got))[:200]
            self._lab_mark_check(st, x, st.note, detail=words)
            self._save()
        if st.status == "error":
            note = str(st.note or "")
            words = words or (note.split(": ", 1)[1] if note.startswith(("entry: ", "upper leg: ", "lower leg: "))
                              else note)
            if any(i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id)):
                pass                                # ids are known: the clock reads them (_lab_settle)
            elif note == "account not connected":   # refused before anything left
                x["clean"] = True
            elif len(legs) == 2:                    # _place cancels the survivor and keeps no id: unreadable
                self._lab_mark_check(st, x, f"a pair's placement failed ({note}); the other leg's id is not kept",
                                     detail=words)
            elif not self._lab_clear_reject(note[len("entry: "):] if note.startswith("entry: ") else note):
                # no answer, an empty one, or words nobody has proven to be a reject: the order may be there
                self._lab_mark_check(st, x, f"the entry's outcome is unknown ({note})", detail=words)
            elif not x.get("check"):                # a clear refusal: nothing is at the broker
                x["clean"] = True
            self._lab_stamp(st, x)
            self._lab_save()
        if st.status in ("placed", "live"):
            for g in legs:                          # I1: every entry has a stop, and the desk must know its order
                sl_id, tp_id = (st.up_sl_id, st.up_tp_id) if g.side == "Buy" else (st.dn_sl_id, st.dn_tp_id)
                if not sl_id or (g.tp_px is not None and not tp_id):
                    x["blind"] = True
            if x["blind"]:
                self._lab_mark_check(st, x, "the broker's answer named no stop order (or no target order)",
                                     why=LAB_NO_STOP_ID)
                ans = {**ans, "warning": LAB_NO_STOP_ID}
        if isinstance(got, dict) and got.get("ok"):
            return ans
        if isinstance(got, Exception) and st.status in ("placed", "live", "done"):
            # S3: the broker acknowledged it and a later step here raised: it IS a trade of this round
            return {**ans, "warning": f"placed; a later step failed: {type(got).__name__}: {got}"[:200]}
        if st.status == "error" and st.note == "account not connected":
            return {"ok": False, "round": ans["round"], "reason": LAB_NOT_CONNECTED}
        if len(legs) == 1 and x.get("check"):       # outcome unknown: "refused" would be a guess. The venue's
            return {"ok": False, "round": ans["round"], "reason": LAB_BAD_ORDER,     # words ride along
                    **({"detail": words} if words and words != "None" else {})}
        if isinstance(got, dict) and "rejected: " in str(got.get("reason")):
            return {"ok": False, "round": ans["round"],
                    "reason": "The broker refused it: " + str(got["reason"]).split("rejected: ", 1)[1]}
        if isinstance(got, dict) and str(got.get("reason", "")).startswith("account stopped"):
            return {"ok": False, "round": ans["round"], "reason": LAB_ACCOUNT_STOPPED}
        return {"ok": False, "round": ans["round"], "reason": LAB_BAD_ORDER,
                **({"detail": words} if words and words != "None" else {})}

    async def lab_enter(self, name: str, legs: list, sizes: dict, *, max_rounds: int,
                        source: str = "lab") -> dict:
        """A Lab strategy's entry (one LabLeg, or a buy-stop / sell-stop pair) on every account in `sizes`
        ({account: contracts}), each as a new ROUND: one position at a time per account, a new round only after
        the last one's orders were read terminal, the account's position read first, the round on disk before
        its order leaves. The accounts go side by side. Disarmed: journaled only (`dry_run`), no state.
        -> {"armed": bool, "accounts": {account: {"ok", "round", "reason"[, "detail"][, "warning"]}}}
           (+ "reason" when the whole call was refused)"""
        sizes = dict(sizes or {})

        def refused(reason: str, armed: Optional[bool] = None) -> dict:
            return {"armed": bool(self.cfg.armed) if armed is None else armed, "reason": reason,
                    "accounts": {a: {"ok": False, "round": None, "reason": reason} for a in sizes}}

        cfg, why = self._lab_may_enter(name)
        if why in (LAB_NOT_ON_DESK, LAB_OFF, LAB_KILLED):
            return refused(why)
        bad = self._lab_bad_legs(legs)
        if bad is not None:
            return refused(bad)
        if why == LAB_TOO_LATE:
            return refused(why)
        legs = list(legs)
        if why == LAB_DISARMED:
            ev = "shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run"
            for a, q in sizes.items():
                self.journal(ev, strategy=name, source=source, account=a, qty=q, legs=[asdict(g) for g in legs])
            return refused(LAB_DISARMED, armed=False)
        self._lab_roll()
        t0 = time.time()
        order = list(sizes)
        if self.rotating(name):
            # one account takes it: the first in turn that opens a round (one that sits out, or whose position is
            # not flat, passes the turn on). The door's refusals never got here: those accounts are not in `sizes`.
            tried = {}
            for a in (a for a in self._turn_order(name) if a in sizes):
                try:
                    tried[a] = await self._lab_enter_one(name, a, sizes[a], legs, max_rounds, source, t0)
                    went = tried[a].get("round") is not None
                except Exception:  # noqa: BLE001 -- answered as the gather below answers it; the outcome is unknown,
                    tried[a], went = {"ok": False, "round": None, "reason": LAB_BAD_ORDER}, True  # so no other account
                if went:
                    self._turn_taken(name, a)
                    break
            else:
                self._no_turn(name, {a: r.get("reason") for a, r in tried.items()})
            return {"armed": bool(self.cfg.armed), "accounts": tried}
        outs = await asyncio.gather(*(self._lab_enter_one(name, a, sizes[a], legs, max_rounds, source, t0)
                                      for a in order), return_exceptions=True)
        return {"armed": bool(self.cfg.armed),
                "accounts": {a: (o if isinstance(o, dict) else {"ok": False, "round": None, "reason": LAB_BAD_ORDER})
                             for a, o in zip(order, outs)}}

    # --- a closed round's orders (I-2) -------------------------------------------------------------
    async def _lab_settle(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> None:
        """Read every order id a terminal round placed. All terminal -> the round is clean (`lab_settled`) and a
        new one may follow. A working ENTRY leftover is cancelled (a later fill would be a new entry); a working
        stop / target only when the account's net in the market reads zero -- protection is never taken from a
        position. An entry that filled on a side the round never held, or anything unread: not clean, `lab_check`."""
        x = self._lab_x(st)
        if st.status not in ("done", "error") or x.get("clean") or not ad.connected:
            return
        if self._lab_stuck(st, x):
            return
        key = self._lab_key(st) or f"{st.strategy}@{st.account}"
        tries = self.__dict__.setdefault("_lab_tries", {})
        gap = LAB_SETTLE_S if tries.get(key, 0) < LAB_SETTLE_FAST else LAB_CHECK_RETRY_S
        if tries.get(key) and time.time() - self._retry_at.get(f"settle:{key}", 0.0) < gap:
            return
        self._retry_at[f"settle:{key}"] = time.time()
        tries[key] = tries.get(key, 0) + 1
        work_e, work_b, unread, filled_b, entries_open = [], [], [], [], False
        for i, side in ((st.upper_id, "Buy"), (st.lower_id, "Sell")):
            if not i:
                continue
            try:
                got = await ad.get_order_state(i) or {}
            except Exception:  # noqa: BLE001 -- unread, asked again
                got = {}
            status, filled = got.get("status"), got.get("filled_qty")
            if status == "Filled" or (status in TERMINAL and filled):
                if st.entry_side != side:
                    return self._lab_mark_check(st, x, f"entry {i} filled ({status}) on a side this round never held")
            elif status in WORKING:
                work_e.append(i)
                entries_open = True
            elif status not in TERMINAL:
                unread.append(i)
                entries_open = True
        for i in (st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id):
            if not i:
                continue
            try:
                status = await ad.get_order_status(i)
            except Exception:  # noqa: BLE001
                status = None
            if status in WORKING:
                work_b.append(i)
            elif status == "Filled":
                filled_b.append(i)
            elif status not in TERMINAL:
                unread.append(i)
        if self._archived(st) or st.status not in ("done", "error") or x.get("clean"):
            return                                   # it moved on while the reads ran
        sent = bool(x.get("close_sent_ms"))
        if (sent and filled_b) or len(filled_b) > 1:
            # a close was SENT (its answer may never have come) and a stop / target filled, or both of them did:
            # the account may hold the other side now, with no stop. Never clean; a person looks.
            return self._lab_mark_check(
                st, x, f"exit orders filled: {', '.join(filled_b)}" + (" and a close order was sent" if sent else ""),
                why=LAB_EXIT_TWICE)
        if not (work_e or work_b or unread):
            if x.get("unconfirmed"):
                # the close was sent and never confirmed: clean needs BOTH facts, every order ended (read above)
                # AND the account flat in the market. Not flat: the close and an exit may both have filled.
                try:
                    net = await ad.get_net_position(cfg.symbol)
                    net = None if net is None or isinstance(net, bool) else int(net)
                except Exception:  # noqa: BLE001 -- unreadable is NOT flat: asked again
                    net = None
                if self._archived(st) or st.status not in ("done", "error") or x.get("clean"):
                    return
                if net is None:
                    return
                if net:
                    # M2: one position read can lag. Three in a row, at least 2 s apart, before it is for good
                    now, last = self._lab_ms(), x.get("net_bad_ms")
                    if last is None or now - last >= LAB_NET_AGAIN_MS:
                        x["net_bad"], x["net_bad_ms"] = int(x.get("net_bad") or 0) + 1, now
                        self._lab_save()
                    if x["net_bad"] < 3:
                        return
                    return self._lab_mark_check(
                        st, x, f"a close was sent and never confirmed, and the account holds {net:+d} {cfg.symbol}",
                        why=LAB_EXIT_TWICE)
                x["unconfirmed"], x["net_bad"], x["net_bad_ms"] = False, 0, None
            x["clean"], x["why"] = True, None
            tries.pop(key, None)
            self.__dict__.get("_lab_said", {}).pop(f"settle:{key}", None)
            self._lab_stamp(st, x)
            self._lab_save()
            self.journal("lab_settled", strategy=st.strategy, account=st.account, round=x.get("round"))
            return
        acts: list[str] = []
        for i in work_e:
            try:
                r = await ad.cancel_order_by_id(i)
            except Exception as e:  # noqa: BLE001 -- asked again on the next read
                r = OrderResult(ok=False, error=str(e))
            acts.append(f"cancel entry {i}: " + ("ok" if r.ok else str(r.error)))
        if work_b and entries_open:
            # R-C: never on a position read alone. While an entry of the round is not read ended it can still
            # fill, and its stop / target are what it would fill with
            acts.append("an entry of this trade is not ended at the broker — stop/target left working")
        elif work_b:
            try:
                net = int(await ad.get_net_position(cfg.symbol) or 0)
            except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
                net = None
                acts.append(f"position unreadable ({e}) — stop/target left working")
            if net == 0:
                await self._cancel_brackets(st, ad, acts)
            elif net is not None:
                acts.append(f"the account holds {net:+d} {cfg.symbol} — stop/target left working")
        acts += [f"order {i}: status unknown" for i in unread]
        said = self.__dict__.setdefault("_lab_said", {})
        if said.get(f"settle:{key}") != acts:
            said[f"settle:{key}"] = acts
            x["why"] = LAB_CANNOT_CHECK
            self._lab_save()
            self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                         reason="orders of the last trade are not all ended", actions=acts)

    # --- lab_cancel -----------------------------------------------------------------------------------
    async def _lab_acked(self, st: DayState) -> bool:
        """Wait (3 s at most) for a round whose placement acks are still out. True = its ids are known."""
        for _ in range(KILL_POLL_N):
            if st.status != "placing":
                break
            await self._kill_sleep(KILL_POLL_S)
        return st.status != "placing"

    async def _lab_hints(self, st: DayState, ad: BrokerAdapter, x: dict) -> None:
        """O-1: the sides a file said were cancelled, read at the broker (every 5 s until each one reads). Ended
        with no fill: it becomes a fact again. Anything else that reads: the hint is dropped. Reads only."""
        hints = [s for s in x.get("cancelled_hint") or [] if s in ("Buy", "Sell")]
        key = f"hint:{st.strategy}@{st.account}"
        if not hints or not ad.connected or time.time() - self._retry_at.get(key, 0.0) < LAB_FLAT_RETRY_S:
            return
        self._retry_at[key] = time.time()
        for s in hints:
            i = st.upper_id if s == "Buy" else st.lower_id
            if i:
                try:
                    got = await ad.get_order_state(i) or {}
                except Exception:  # noqa: BLE001 -- unread: asked again
                    continue
                status, filled = got.get("status"), got.get("filled_qty")
                if status is None:
                    continue
                if status in TERMINAL and status != "Filled" and not filled \
                        and not (st.entry_side == s and st.entry_qty) and s not in x["cancelled"]:
                    x["cancelled"].append(s)
            if s in x["cancelled_hint"]:
                x["cancelled_hint"].remove(s)
        self._lab_save()

    async def _lab_end_unfilled(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, acts: list) -> bool:
        """Every entry of the round ended with no fill: the round is done / "cancelled". R-C: first every entry is
        READ ended with no fill at the broker, here, whatever the caller or a file believes; one that is not:
        "check it", nothing is ended and nothing cancelled (False). Its stop and target died with their entries;
        they are cancelled for good measure ONLY when the account's net in the market reads zero (a fill push
        can be missed: never take a stop from a position), as the kill does. True = the round was ended."""
        x = self._lab_x(st)
        if not await self._lab_entries_ended(st, ad, x, acts, unfilled=True):
            return False
        if self._archived(st) or st.status not in ("placed", "live"):
            return False                             # the read yielded: it moved on by itself
        st.status, st.exit_reason = "done", "cancelled"
        self._lab_stamp(st, x)
        self._save()
        try:
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
            acts.append(f"position unreadable ({e}) — stop/target left alone")
            return True
        if net:
            acts.append(f"the account holds {net:+d} {cfg.symbol} — stop/target left alone")
            return True
        await self._cancel_brackets(st, ad, acts)
        return True

    async def _lab_cancel_one(self, st: DayState, cfg: StrategyCfg, iid: Optional[int], why: str) -> dict:
        acts: list[str] = []
        ad = self.adapters.get(st.account)
        if ad is None:
            return {"ok": st.status not in ("placing", "placed"), "state": "working" if st.status in
                    ("placing", "placed") else "none", "actions": ["account not connected"]}
        if not await self._lab_acked(st):
            return {"ok": False, "state": "working", "actions": ["its orders are not acknowledged yet"]}
        x = self._lab_x(st)
        if x.get("lost") and st.status in ("placed", "live"):
            return {"ok": False, "state": "working", "actions": [LAB_LOST_ACT]}
        ids = {"Buy": st.upper_id, "Sell": st.lower_id}
        asked = [s for s in ("Buy", "Sell") if ids[s] and (iid is None or (x.get("iid") or {}).get(s) == iid)]
        if not asked or st.status not in ("placed", "live"):
            return {"ok": True, "state": "none", "actions": acts}
        seen = {s: "cancelled" for s in asked if s in x["cancelled"]}
        part = 0
        if st.status == "live" and st.entry_side in asked and st.qty and st.entry_qty >= st.qty:
            seen[st.entry_side] = "filled"           # every contract is in: nothing of it is left to cancel
        todo = [s for s in asked if s not in seen]
        res = await asyncio.gather(*(ad.cancel_order_by_id(ids[s]) for s in todo), return_exceptions=True)
        for s, r in zip(todo, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel entry {ids[s]}: " + ("ok" if ok else str(r if isinstance(r, Exception) else r.error)))
        states = await self._entry_states(ad, [ids[s] for s in todo]) if todo else {}
        # the poll yielded: from here to the end of the block nothing awaits, so what is read is what is written
        done_now = []
        for s in todo:
            status, filled = states[ids[s]]
            got = int(filled or 0) or (int(st.entry_qty or 0) if st.entry_side == s else 0)
            if status == "Filled":
                seen[s] = "filled"                   # the fill beat the cancel: on_fill / the clock take it live
                self.journal("lab_cancel_raced_fill", strategy=st.strategy, account=st.account,
                             round=x.get("round"), iid=(x.get("iid") or {}).get(s), order_id=ids[s],
                             status=status, filled=filled)
            elif status in TERMINAL and got:
                seen[s], part = "part", part + got   # the rest is cancelled; what is in keeps its stop
                self.journal("lab_cancelled", strategy=st.strategy, account=st.account, round=x.get("round"),
                             sides=[s], iids=[(x.get("iid") or {}).get(s)], why=why, ended=False,
                             part=got, actions=list(acts))
            elif status in TERMINAL:
                seen[s] = "cancelled"
                if s not in x["cancelled"]:
                    x["cancelled"].append(s)
                    done_now.append(s)
            else:
                seen[s] = "working"                  # not resolved: the round stays as it is, and it says so
                self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                             reason=f"entry {ids[s]} not cancelled or filled ({status or 'status unknown'})",
                             actions=list(acts))
        ended = (not self._archived(st) and st.status == "placed"
                 and all(s in x["cancelled"] for s in ("Buy", "Sell") if ids[s]))
        if ended:
            ended = await self._lab_end_unfilled(st, cfg, ad, acts)
            if not ended and st.status == "placed":  # an entry did not read ended with no fill after all
                seen = {s: "working" for s in seen}
        self._lab_save()
        if done_now or ended:
            self.journal("lab_cancelled", strategy=st.strategy, account=st.account, round=x.get("round"),
                         sides=done_now, iids=[(x.get("iid") or {}).get(s) for s in done_now], why=why,
                         ended=ended, actions=acts)
        state = next(k for k in ("working", "part", "filled", "cancelled") if k in seen.values())
        return {"ok": state != "working", "state": state, "actions": acts,
                **({"filled": part} if state == "part" else {})}

    async def lab_cancel(self, name: str, iid: Optional[int] = None, *, why: str = "cancel") -> dict:
        """Cancel a Lab strategy's unfilled entry (its own order id `iid`; None = every unfilled entry) on every
        account with an open round. A cancel "ok" is not cancelled: each entry is read back (3 s at most).
        Ended with no fill -> that leg is cancelled, and a round with no working leg left is done / "cancelled".
        Filled -> nothing more (the position keeps its broker stop). Neither -> the round stays, `lab_check`.
        Never a market order. -> {account: {"ok", "state": "cancelled|filled|working|none", "actions"}}"""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return {}
        self._lab_roll()
        rounds = {st.account: st for st in self.day_states(name)
                  if not self._archived(st) and st.status != "idle"}

        async def account(a: str) -> dict:
            return await self._lab_cancel_one(rounds[a], cfg, iid, why)

        got, _ = await self.each_account(rounds, account)
        return {a: (g if isinstance(g, dict) else
                    {"ok": False, "state": "working", "actions": [f"internal error: {type(g).__name__}: {g}"]})
                for a, g in got.items()}

    # --- the capped flatten ---------------------------------------------------------------------------
    def _lab_unconfirmed(self, st: DayState, x: dict, acts: list, reason: str) -> None:
        """The one market-out was refused, or its outcome is not known: "check it". Nothing more is sold for this
        round by the engine; its stop stays. Journaled once (`lab_check`)."""
        acts.append("check it — the close order was not confirmed; its stop is still working")
        if x.get("unconfirmed"):
            return
        x["unconfirmed"], x["why"] = True, LAB_CLOSE_UNCONFIRMED
        self._lab_save()
        try:
            self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                         reason=reason, actions=list(acts))
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)

    async def _lab_finish(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict, acts: list,
                          reason: str, *, cancel: bool) -> None:
        """The round's position is gone and no exit fill closed it here: done, with no fill price to book
        (`lab_exit_unconfirmed`). cancel: the account read flat just now, so the stop / target go too."""
        st.status, st.exit_reason = "done", reason
        if st.exit_fill is not None and st.pnl is None:
            st.pnl = self._gross_pnl(st, cfg)       # the part whose exit fills were seen
        x["unconfirmed"] = False
        if x.get("why") == LAB_CLOSE_UNCONFIRMED:
            x["why"] = None
        self._lab_mark_check(st, x, "the round ended with no exit fill seen")
        self._lab_stamp(st, x)
        self._save()
        self._lab_save()
        self.journal("lab_exit_unconfirmed", strategy=st.strategy, account=st.account, round=x.get("round"),
                     reason=reason, entered=st.entry_qty, out=st.exit_qty)
        if cancel:
            await self._cancel_brackets(st, ad, acts)

    async def _lab_entries_ended(self, st: DayState, ad: BrokerAdapter, x: dict, acts: list,
                                 unfilled: bool = False) -> bool:
        """R-C: before a round is ended, or its stop / target cancelled, on a position read: every entry of the
        round must READ ended at the broker, now (only one whose every contract was seen filled here is not asked:
        it can fill no more). One that does not: "check it", and the caller ends and cancels nothing. A cancel that
        was accepted is not a cancelled order, and a mark in a file is not a read."""
        for s, i in (("Buy", st.upper_id), ("Sell", st.lower_id)):
            if not i or (st.entry_side == s and st.qty and st.entry_qty >= st.qty):
                continue
            try:
                got = await ad.get_order_state(i) or {}
            except Exception:  # noqa: BLE001 -- unread is not ended
                got = {}
            if got.get("status") not in TERMINAL:
                acts.append(f"check it — entry {i} is not ended at the broker ({got.get('status') or 'status unknown'}); "
                            "nothing is ended or cancelled")
                return False
            if unfilled and (got.get("status") == "Filled" or got.get("filled_qty")):
                acts.append(f"check it — entry {i} filled ({got.get('status')}); nothing is ended or cancelled")
                return False
        return True

    async def _lab_close_retry(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict,
                               acts: list) -> dict:
        """A flatten of a round whose ONE market-out already left (or that already read flat): reads only, never
        a second order. Flat for LAB_UNCONFIRMED_S with no exit fill, and every entry read ended -> the round
        ends. Still holding after that, or after a refused close -> "check it", stops left working."""
        def ans(ok: bool) -> dict:
            return {"ok": ok, "sold": 0, "actions": acts}

        now = self._lab_ms()
        if not x.get("close_sent_ms"):               # it read flat with every entry ended: nothing was sent
            if now - int(x.get("gone_ms") or now) < LAB_UNCONFIRMED_S * 1000:
                acts.append("the account is already flat")
                return ans(True)
            if not await self._lab_entries_ended(st, ad, x, acts):
                return ans(False)
            if st.status in ("placed", "live"):
                await self._lab_finish(st, cfg, ad, x, acts, "exit", cancel=False)
            return ans(True)
        try:
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
            acts.append(f"check it — position unreadable ({e}); stops left working")
            return ans(False)
        if st.status not in ("placed", "live"):
            acts.append("This trade had already ended.")     # its exit fill closed it meanwhile
            return ans(True)
        waited = now - int(x.get("close_sent_ms") or now) >= LAB_UNCONFIRMED_S * 1000
        if net == 0:
            if x.get("unconfirmed") or waited:
                if not await self._lab_entries_ended(st, ad, x, acts):
                    return ans(False)
                if st.status in ("placed", "live"):
                    await self._lab_finish(st, cfg, ad, x, acts, str(x.get("closing") or "flat"), cancel=True)
            else:
                acts.append("the account is already flat")
            return ans(True)
        if not x.get("unconfirmed") and not waited:
            acts.append("the close order is out: waiting for its fill")
            return ans(True)
        self._lab_unconfirmed(st, x, acts, "the close order is out and the position is still there")
        return ans(False)

    async def _lab_entry_states(self, ad: BrokerAdapter, ids: list, quick: bool) -> dict:
        """_entry_states for a flatten asked for by hand (3 s at most). quick, for the clock: LAB_CLOCK_POLLS
        re-reads at most (half a second) -- the clock comes back every 5 s by itself, and every other
        strategy's tick waits for this one."""
        if not quick:
            return await self._entry_states(ad, ids)
        out: dict = {}
        for attempt in range(LAB_CLOCK_POLLS + 1):
            for i in ids:
                if i in out and out[i][0] in TERMINAL:
                    continue
                try:
                    got = await ad.get_order_state(i) or {}
                except Exception:  # noqa: BLE001 -- unknown, asked again
                    got = {}
                out[i] = (got.get("status"), got.get("filled_qty"))
            if all(out[i][0] in TERMINAL for i in ids) or attempt == LAB_CLOCK_POLLS:
                break
            await self._kill_sleep(KILL_POLL_S)
        return out

    async def _lab_flatten_one(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, reason: str,
                               quick: bool = False) -> dict:
        """Close ONE round's own position (called under the strategy's kill lock). Never more than its own filled
        quantity, only on its side, never the account-wide calls, and ONE market order per round, ever.
          1. cancel every entry not known ended; read each back (3 s at most). One that is neither cancelled
             nor filled -> "check it": nothing sold, stops stay;
          2. own quantity: the round's size for an entry that reads Filled, the broker's filled quantity for one
             cancelled after a part fill, less the exit fills seen. Nothing ever filled -> the round is done /
             "cancelled" and no order is sent;
          3. read the net: unreadable or on the other side -> "check it". Zero -> the stop / target go, the round
             waits for its exit fill;
          4. market out min(|net|, own), text homebase:lab-flat. `closing` is on disk before it leaves. Refused
             -> "check it", stops stay, never sent again;
          5. accepted -> the stop / target are cancelled; the round stays live until the exit fill books it.
        -> {"ok", "sold": contracts, "actions"}"""
        acts: list[str] = []
        x = self._lab_x(st)
        reason = str(reason or "flat")               # never empty: it becomes the round's exit reason

        def ans(ok: bool, sold: int = 0) -> dict:
            return {"ok": ok, "sold": sold, "actions": acts}

        def unsure(why: str) -> dict:
            acts.append(f"check it — {why}; nothing sold; stops left working")
            return ans(False)

        if st.status not in ("placed", "live"):
            return ans(True)
        if x.get("lost"):                            # R-B: nothing is sent or cancelled for a trade whose record is lost
            acts.append(LAB_LOST_ACT)
            return ans(False)
        if x.get("close_sent_ms") or x.get("gone_ms"):
            await self._lab_cancel_entries(st, ad, x, acts)      # a cancel is always safe; never a second close
            return await self._lab_close_retry(st, cfg, ad, x, acts)
        ids = {"Buy": st.upper_id, "Sell": st.lower_id}                     # 1
        held = {"Buy": 0, "Sell": 0}
        ask = []
        bound = False                                # own quantity is the broker's count for a part fill: a lower bound
        for s in ("Buy", "Sell"):
            if not ids[s] or (s in x["cancelled"] and not (st.entry_side == s and st.entry_qty)):
                continue                             # ended with no fill (a mark that the fills contradict is not believed)
            if st.entry_side == s and st.qty and st.entry_qty >= st.qty:
                held[s] = int(st.qty)                # every contract's fill was seen here: it can fill no more
            else:
                ask.append(s)
        res = await asyncio.gather(*(ad.cancel_order_by_id(ids[s]) for s in ask), return_exceptions=True)
        for s, r in zip(ask, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel entry {ids[s]}: " + ("ok" if ok else str(r if isinstance(r, Exception) else r.error)))
        states = await self._lab_entry_states(ad, [ids[s] for s in ask], quick) if ask else {}
        if st.status not in ("placed", "live"):      # the poll yielded: the round may have ended by itself
            acts.append("This trade had already ended.")
            return ans(True)
        doubt = []
        for s in ask:                                                       # 2
            status, filled = states[ids[s]]
            if status == "Filled":
                held[s] = int(st.qty or 0)
            elif status in TERMINAL and filled:
                held[s], bound = int(filled), True
            elif status in TERMINAL and st.entry_side == s and st.entry_qty:
                doubt.append(f"entry {ids[s]} {status.lower()}, its filled quantity is not known")
            elif status in TERMINAL:
                if s not in x["cancelled"]:
                    x["cancelled"].append(s)
            else:
                doubt.append(f"entry {ids[s]} not cancelled or filled ({status or 'status unknown'})")
        if doubt:
            return unsure("; ".join(doubt))
        if held["Buy"] and held["Sell"]:
            return unsure("both entries filled")
        side = "Buy" if held["Buy"] else "Sell" if held["Sell"] else None
        if side is None:                             # nothing of this round ever filled
            if not await self._lab_end_unfilled(st, cfg, ad, acts):
                if st.status not in ("placed", "live"):      # it ended by itself during the read
                    acts.append("This trade had already ended.")
                    return ans(True)
                return ans(False)
            self._lab_save()
            self.journal("lab_cancelled", strategy=st.strategy, account=st.account, round=x.get("round"),
                         sides=list(x["cancelled"]), iids=list((x.get("iid") or {}).values()), why=reason,
                         ended=True, actions=acts)
            return ans(True)
        if x.get("blind"):
            return unsure("the Desk does not know this trade's stop order and could not cancel it")
        try:                                                                # 3
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
            return unsure(f"position unreadable ({e})")
        if st.status not in ("placed", "live"):      # the read yielded too: re-checked right before any sale
            acts.append("This trade had already ended.")
            return ans(True)
        if st.status == "placed" or st.entry_side != side:    # the entry is in and its fill push never came
            st.status, st.entry_side = "live", side
            st.entry_anchor = st.upper_px if side == "Buy" else st.lower_px
            st.note = "fill push missed — entry found by the flatten"
            self._save()
        own = held[side] - int(st.exit_qty or 0)
        if own <= 0:                                 # every contract that went in is out again
            await self._close_if_out(st, cfg, ad)
            acts.append("nothing of its own is left to close")
            return ans(True)
        if net == 0:
            acts.append("the account is already flat")
            x["gone_ms"] = self._lab_ms()
            self._lab_save()
            await self._cancel_brackets(st, ad, acts)
            return ans(True)
        if (net > 0) != (side == "Buy"):
            return unsure(f"the account's {net:+d} {cfg.symbol} is not on its side")
        if bound and abs(net) != own:
            # a fill push without its order id is not counted (broker/tradovate.py _count_fill): selling the
            # count and cancelling the stop could leave a contract with nothing behind it
            return unsure(f"the entry was cancelled part filled: {own} counted, the account holds {net:+d} {cfg.symbol}")
        qty, out_side = min(abs(net), own), ("Sell" if side == "Buy" else "Buy")     # 4
        x["closing"], x["close_sent_ms"] = reason, self._lab_ms()
        try:
            self._lab_save(strict=True)              # on disk first: a restart must not send it a second time
        except Exception as e:  # noqa: BLE001 -- nothing was sent
            x["closing"] = x["close_sent_ms"] = None
            return unsure(f"the close could not be written down ({e})")
        try:
            r = await ad.place_order(OrderRequest(symbol=cfg.symbol, side=out_side, qty=qty,
                                                  order_type="Market", text=LAB_FLAT_TEXT))
        except Exception as e:  # noqa: BLE001 -- it may have gone out anyway
            r = OrderResult(ok=False, error=str(e))
        acts.append(f"market {out_side} {qty}: {'ok' if r.ok else r.error}")
        if not r.ok:
            self._lab_unconfirmed(st, x, acts, "the market-out reported failure")
            return ans(False)
        x["close_ok"], x["close_id"] = True, r.order_id
        self._lab_save()
        if st.status not in ("placed", "live"):      # the send yielded: the round's own stop / target ended it
            acts.append(f"the round ended while the close was sent ({st.exit_reason})")
            return ans(True, qty)                    # nothing is cancelled; the settle sees a double exit
        await self._cancel_brackets(st, ad, acts)                           # 5
        return ans(True, qty)

    async def lab_flatten(self, name: str, *, reason: str = "flat") -> dict:
        """Close a Lab strategy's OWN position on every account with an open round (see _lab_flatten_one), under
        the strategy's kill lock, the accounts side by side. `reason` becomes the round's exit reason when its
        exit fill arrives. -> {account: {"ok", "sold", "actions"}}; journals `lab_flatten`."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return {}
        reason = str(reason or "flat")
        self._lab_roll()
        async with self._kill_lock(name):
            rounds = {st.account: st for st in self.day_states(name)     # read INSIDE the lock
                      if not self._archived(st) and st.status != "idle"}

            async def account(a: str) -> dict:
                st = rounds[a]
                ad = self.adapters.get(a)
                if ad is None:
                    return {"ok": st.status not in ("placing", "placed", "live"), "sold": 0,
                            "actions": ["account not connected"]}
                if not await self._lab_acked(st):
                    return {"ok": False, "sold": 0, "actions": ["check it — its orders are not acknowledged yet"]}
                return await self._lab_flatten_one(st, cfg, ad, reason)

            got, _ = await self.each_account(rounds, account)
            results = {a: (g if isinstance(g, dict) else
                           {"ok": False, "sold": 0, "actions": [f"internal error: {type(g).__name__}: {g}"]})
                       for a, g in got.items()}
            if results:
                self._save()
                self._lab_save()
                self.journal("lab_flatten", strategy=name, reason=reason, results=results)
        return results

    # --- hooks 6 and 8: a Kill never sends a second market order for a round whose close is out ------
    def _lab_close_sent(self, st: DayState) -> bool:
        """An open round the global Kill's per-strategy pass leaves to its own account sweep: its ONE market-out
        has been sent (accepted, refused or unknown), or its record was lost (hands off)."""
        if st.status not in ("placed", "live"):
            return False
        x = self._lab_x(st)
        return bool(x.get("close_sent_ms") or x.get("lost"))

    def _lab_hands_off(self, st: DayState) -> bool:
        """A round the per-strategy Kill takes through its Lab path: its close is out (or may be), or it read flat
        with its entries ended (a position on the account now is not its own), or it is filed away (I-4), or
        the Desk does not know its stop order, or its record was lost."""
        if self._archived(st):
            return True
        x = self._lab_x(st)
        return st.status in ("placed", "live") and bool(
            x.get("close_sent_ms") or x.get("gone_ms") or x.get("blind") or x.get("lost"))

    async def _lab_cancel_entries(self, st: DayState, ad: BrokerAdapter, x: dict, acts: list) -> None:
        """Cancel the round's entries that are not known ended. Never an order that could open or close anything."""
        for s, i in (("Buy", st.upper_id), ("Sell", st.lower_id)):
            if not i or s in x["cancelled"] or (st.entry_side == s and st.qty and st.entry_qty >= st.qty):
                continue
            try:
                r = await ad.cancel_order_by_id(i)
            except Exception as e:  # noqa: BLE001
                r = OrderResult(ok=False, error=str(e))
            acts.append(f"cancel entry {i}: " + ("ok" if r.ok else str(r.error)))

    async def _lab_kill_readonly(self, st: DayState, cfg: StrategyCfg, account: str) -> dict:
        """The per-strategy Kill's Lab path (hook 8).
          a carried block            nothing is sent: "check it";
          a close that is (or may be) out, or a round that read flat
                                     cancel its unfilled entries, read, "check it". Never a market order, never
                                     _kill_state;
          a stop order the Desk does not know (and no close sent)
                                     the Kill closes the position as a Kill does (_kill_state, unchanged), and
                                     its answer is ok False: that stop may still be working at the broker."""
        acts: list[str] = []
        if self._archived(st):
            return {"ok": False, "actions": ["check it — an earlier trade of this strategy is not resolved on this "
                                             "account; nothing is sent"]}
        x = self._lab_x(st)
        if x.get("lost"):                            # R-B: hands off -- nothing is cancelled, nothing is sent
            return {"ok": False, "actions": [LAB_LOST_ACT]}
        ad = self.adapters.get(account)
        if ad is None:
            return {"ok": False, "error": "account not connected", "actions": acts}
        if not (x.get("close_sent_ms") or x.get("gone_ms")):     # blind, no close sent
            res = await self._kill_state(st, cfg, ad)
            acts = list(res["actions"]) + ["check it — this trade's stop order is unknown to the Desk and may still "
                                           "be working"]
            try:
                self.journal("lab_check", strategy=st.strategy, account=account, round=x.get("round"),
                             reason="a kill of a round whose stop order the Desk does not know", actions=acts)
            except Exception as e:  # noqa: BLE001
                print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)
            return {"ok": False, "acted": True, "actions": acts}
        await self._lab_cancel_entries(st, ad, x, acts)
        await self._lab_close_retry(st, cfg, ad, x, acts)        # reads only; ends the round if the account is flat
        if st.status in ("placed", "live") and not any(a.startswith("check it") for a in acts):
            acts.append("check it — its close order is already out; nothing more is sold")
        return {"ok": st.status not in ("placed", "live"), "acted": True, "actions": acts}

    # --- hook 5: the Desk's "Flatten & turn off" --------------------------------------------------
    async def _lab_flatten_strategy(self, name: str) -> dict:
        """flatten_strategy for kind lab: the capped flatten, answered in flatten_strategy's own shape
        ({account: [actions]}) and journaled as `manual_flatten`."""
        t0 = self._perf()
        results = {a: r["actions"] for a, r in (await self.lab_flatten(name, reason="manual_flat")).items()}
        self.journal("manual_flatten", strategy=name, results=results,
                     flatten_ms={"total": round((self._perf() - t0) * 1000, 1)})
        return results

    # --- hook 7: the clock, for the open round only -----------------------------------------------
    async def _lab_tick_flat(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict, key: str) -> None:
        """The clock's capped flatten: every LAB_FLAT_RETRY_S (a "check it" close: LAB_CHECK_RETRY_S), and only
        when the strategy's kill lock is free -- a Kill or a flatten in progress is never waited for here, so
        another strategy's tick on this account is not held up behind it."""
        said = self.__dict__.setdefault("_lab_said", {})
        if not ad.connected:                         # nothing is sent blind: the one close is not used up
            if said.get(f"wait:{key}") != x.get("round"):
                said[f"wait:{key}"] = x.get("round")
                self.journal("clock_flat_waiting", strategy=st.strategy, account=st.account,
                             round=x.get("round"), reason="account not connected")
            return
        gap = LAB_CHECK_RETRY_S if x.get("unconfirmed") else LAB_FLAT_RETRY_S
        rk = f"flat:{key}"
        lock = self._kill_lock(st.strategy)
        if time.time() - self._retry_at.get(rk, 0.0) < gap or lock.locked():
            return
        self._retry_at[rk] = time.time()
        t = self._perf()
        async with lock:                             # free: taken at once, with no wait
            res = await self._lab_flatten_one(st, cfg, ad, "flat", quick=True)
        self._save()
        self._lab_save()
        told = ("ok", x.get("round")) if res["ok"] else ("failed", x.get("round"), tuple(res["actions"]))
        if said.get(rk) == told or (res["ok"] and not res["actions"]):
            return                                   # said already: one line per round that closed, one per new failure
        said[rk] = told
        self.journal("clock_flat" if res["ok"] else "clock_flat_failed", strategy=st.strategy,
                     account=st.account, actions=res["actions"],
                     flat_ms=round((self._perf() - t) * 1000, 1))      # timing only

    async def _lab_tick(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, now: dt.time) -> None:
        """One clock tick of a Lab strategy's OPEN round (an archived one is never acted on: I-4).
          placed, before flat_et      the order-status backstop for a missed fill push (_guard_placed)
          placed or live at flat_et   the capped flatten (never a "check it" run of a killed strategy)
          a close already under way   read again every 5 s, also before flat_et; never a second order
          live with exit fills        is the trade over? (_close_if_out)
          live or done, a sibling     is the other entry really gone? (_guard_sibling)
          done or error               are its orders all ended? (_lab_settle)"""
        if self._archived(st):
            if self._lab_carried(st):
                await self._lab_carry_check(st, cfg, ad, self._lab_x(st))
            return
        if st.status == "idle":
            return
        x = self._lab_x(st)
        if self._lab_stamp(st, x):
            self._lab_save()
        if x.get("lost"):
            # R-B: this trade's record was lost. The clock does nothing of the Lab's with it: no flat time, no
            # capped flatten, no cancel, no settle. L-1: ONE thing stays, and it is the engine's own -- while it is
            # placed, before the flat time and with the adapter connected, the order-status backstop that adopts a
            # fill whose push was missed and cancels the pair's other entry, exactly as a healthy placed round has it
            if st.status == "placed" and now < _hhmm(cfg.flat_et) and ad.connected:
                await self._guard_placed(st, cfg, ad, check_position=False, event="entry_found_by_check",
                                         note="fill push missed — entry found by the order-status check")
            return
        await self._lab_hints(st, ad, x)             # O-1: what the file said was cancelled, read at the broker
        key = f"{st.strategy}@{st.account}"
        check_it = self.needs_check(st)              # killed today and still placed / live: a human's job
        if check_it:
            self._journal_needs_check(st, cfg, now)
        late = now >= _hhmm(cfg.flat_et)
        closing = bool(x.get("close_sent_ms") or x.get("gone_ms"))
        if st.status == "placed" and not late and not closing:
            if ad.connected:       # a dead socket's cache is stale; reconnect reconciles
                await self._guard_placed(st, cfg, ad, check_position=False, event="entry_found_by_check",
                                         note="fill push missed — entry found by the order-status check")
        elif st.status in ("placed", "live") and (closing or (late and not check_it)):
            await self._lab_tick_flat(st, cfg, ad, x, key)
        elif st.status == "placed" and late:
            # a killed "check it" run: its entries are still cancelled at the flat time (once); it is never
            # flattened by the clock (as the clock above does for every other kind)
            k = (st.date, st.strategy, st.account)
            if k not in self._check_it_cancelled:
                self._check_it_cancelled.add(k)
                acts = []
                for oid in (st.upper_id, st.lower_id):
                    if oid:
                        r = await ad.cancel_order_by_id(oid)
                        acts.append(f"cancel {oid}: " + ("ok" if r.ok else str(r.error)))
                self.journal("killed_run_entries_cancelled", strategy=st.strategy, account=st.account,
                             actions=acts)
        if st.status == "live" and st.exit_qty and ad.connected:
            await self._close_if_out(st, cfg, ad)   # out, and the rest of the entry was cancelled
        if st.status in ("live", "done") and st.entry_side and ad.connected:
            other = "Sell" if st.entry_side == "Buy" else "Buy"
            if (st.lower_id if st.entry_side == "Buy" else st.upper_id) and other not in x["cancelled"]:
                status = await self._guard_sibling(st, cfg, ad)
                if status in TERMINAL and status != "Filled":
                    x["cancelled"].append(other)     # read ended: never asked again
                    self._lab_save()
        if st.status in ("done", "error"):
            await self._lab_settle(st, cfg, ad)

    # --- (the Lab methods end here) ---
