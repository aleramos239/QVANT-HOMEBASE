"""The desk's side of a promoted Lab strategy (Step B). This file is the CONFIG half (task B1): the desk knows the
strategy, keeps its limits and its book, switches it, removes it and says what it is doing. The INTAKE half (task B3:
the runner's orders, the stream, the heartbeat rule) is added to this class later; until then nothing here, and nothing
that calls it, can send an order.

    attach(cfg)            the desk's start: overlay the promoted strategies on the config, register the sidecar writer
                           as config.save's after-save hook. Never raises: a Lab problem never stops the desk.
    LabDesk.owner()        ONE desk owns a store (labcfg.take_store: <store>/desk.lock). Asked when the desk starts to
                           run or first changes something -- never by a desk that is only built. A desk that is not the
                           owner reads only: it writes no sidecar and refuses every change of a Lab strategy.
    LabDesk.refresh()      every 2 s (run()): the store is read in a thread, the config is changed on the loop. Skipped
                           while the chart views are paused (a bot is placing, the seconds around a fire) and while a
                           request is writing. It never waits for the store's lock.
    LabDesk.set_limits     the owner's limits, checked (labcfg.parse_limits); not 09:20-09:35 ET, not with a round open,
                           not below a size already booked.
    LabDesk.check_book     asked before EVERY strategy's book write: one strategy per market per account when a Lab
                           strategy is one of the two; for a Lab strategy also its limits, its size cap, one broker
                           account once, and no account taken off while it has a round open.
    LabDesk.set_book       a Lab strategy's book: check_book, then its sidecar, then the desk's memory.
    LabDesk.set_enabled    the ONE switch: the store record's `enabled` (the runner hosts by it).
    LabDesk.remove         off the Desk: sidecar and record go, the history stays. Not with a round open.
    LabDesk.status_view    the `lab` block of /api/status.

A change the owner asks for is written FIRST (in a thread, waiting at most REQ_WAIT_S for the store's lock) and becomes
the desk's memory only once it is on disk: a refusal ("Could not save it. Try again.") changes nothing. One change per
strategy at a time; a request that goes away mid-write still ends with memory and disk agreeing (the pair is shielded).

Who is the truth is written in labcfg.py. Strategy code never runs in this process: this module and labcfg import
nothing from homebase.backtest (tests pin it).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import time
from dataclasses import asdict
from typing import Callable

from . import config as config_mod
from . import labcfg
from .config import AppCfg, assignments
from .labcfg import LAB
from .labrun import store

log = logging.getLogger(__name__)

REFRESH_S = 2.0                          # the store is re-read this often
REQ_WAIT_S = 2.0                         # a request waits this long, at most, for the store's lock (in a thread)
RUNNER_ALIVE_S = 20                      # the runner is alive while its heartbeat is at most this old
QUIET = (dt.time(9, 20), dt.time(9, 35))   # weekdays ET: the 9:30 window (limits are not changed in it)
OPEN = ("placing", "placed", "live")     # a round the engine still acts on

NOT_ON_DESK = "That strategy is not on the Desk."
SET_LIMITS_FIRST = "Set the limits first."
FLATTEN_FIRST = "Flatten it first."
NOT_NOW = "Not 09:20-09:35 ET. Try again after 09:35."
NOT_SAVED = "Could not save it. Try again."
RECORD_CHANGED = "The Lab record changed. Try again."
BOOKED_FOR_MORE = "An account is booked for more. Lower its size first."
OTHER_DESK = "Another Desk is running on this store."
CANNOT_READ = "The Desk cannot read it."
CANNOT_READ_LIMITS = "The Desk cannot read its limits."
SWITCH_NOT_OFF = "Flattened. Could not switch it off: try the switch again."


class Refused(Exception):
    """A request the desk will not take. str(e) is the sentence the page shows; `status` is the HTTP status."""

    def __init__(self, sentence: str, status: int = 409):
        super().__init__(sentence)
        self.status = status


def attach(cfg: AppCfg, at=None) -> None:
    """The desk's start, right after config.load(): the promoted strategies join the config in memory (never
    config.json), and every later config.save also writes the sidecars that changed (only for the desk that owns the
    store, and without ever waiting for it). Reads only; never raises."""
    if labcfg.persist_all not in config_mod._after_save:
        config_mod._after_save.append(labcfg.persist_all)
    try:
        labcfg.bind(cfg, at)
        labcfg.overlay(cfg)
    except Exception as e:  # noqa: BLE001 -- the desk starts without them; refresh() tries again every 2 s
        log.warning("the promoted Lab strategies could not be read at the start: %s", e)


class LabDesk:
    def __init__(self, cfg: AppCfg, engine, adapters: dict, *, paused: Callable[[], bool] | None = None, at=None):
        self.cfg, self.engine, self.adapters = cfg, engine, adapters
        self._paused = paused or (lambda: False)
        if at is not None:
            labcfg.bind(cfg, at)
        self._at = cfg.__dict__.get("_lab_at")
        self._gen = 0                    # bumped by every change the desk itself makes: a store read that began
                                         # before one is thrown away (it may hold what the change replaced)
        self._seen_utc: dt.datetime | None = None    # the runner's heartbeat, as last read
        self._said: tuple | None = None  # (error text, monotonic) of the last lab_refresh_error line
        self._said_busy = False          # lab_store_busy is journaled once
        self._said_view: set = set()     # (strategy, error) of the lab_view_error lines

    # ------------------------------------------------------------ one desk owns the store
    def owner(self) -> bool:
        """True for the one desk that writes this store's sidecars. Decided the first time it is asked (run(), a
        refresh, a change) and never again; a desk that is not the owner says so once in the journal."""
        got = labcfg.take_store(self.cfg, self._at)
        if not got and not self._said_busy:
            self._said_busy = True
            self._journal("lab_store_busy", store=str(store.root(self._at)))
        return got

    def close(self) -> None:
        """Give the store back (the desk is shutting down; the OS does the same when the process ends)."""
        labcfg.release_store(self.cfg)

    def _must_own(self) -> None:
        if not self.owner():
            raise Refused(OTHER_DESK)

    # ------------------------------------------------------------ small reads (memory only)
    def is_lab(self, name) -> bool:
        s = self.cfg.strategies.get(name)
        return s is not None and getattr(s, "kind", "") == LAB and labcfg.is_lab(self.cfg, name)

    def _open(self, name: str) -> list[str]:
        """Accounts with a round of this strategy the engine still acts on. engine.lab_open (task B2) adds the rounds
        it cannot yet call clean."""
        out = {st.account for st in self.engine.day_states(name) if st.status in OPEN}
        out |= set(getattr(self.engine, "lab_open", lambda n: [])(name))
        return sorted(out)

    def _label(self, aid: str) -> str:
        a = self.cfg.accounts.get(aid)
        return (a.label or a.account_name or aid) if a is not None else aid

    def _in_quiet(self) -> bool:
        now = self.engine.now_et()
        return now.weekday() < 5 and QUIET[0] <= now.time() < QUIET[1]

    def _need(self, name) -> None:
        if not self.is_lab(name):
            raise Refused(NOT_ON_DESK, 404)

    def _journal(self, event: str, **kw) -> None:
        with contextlib.suppress(Exception):
            self.engine.journal(event, **kw)

    def _say_notes(self) -> None:
        """Journal what the overlay had to say (labcfg.take_notes). A desk that reads only dropped nothing on disk:
        its `lab_unbooked` notes are about its own view and are not journaled."""
        for event, fields in labcfg.take_notes(self.cfg):
            if event == "lab_unbooked" and not labcfg.owns(self.cfg):
                continue
            self._journal(event, **fields)

    # ------------------------------------------------------------ the 2 s refresh
    def _read(self) -> tuple:
        """The disk half, in a thread: every record with its sidecar, and the runner's heartbeat."""
        return labcfg.read_store(self._at), store.get_runner(self._at)

    def _drop_orphan(self, sname: str) -> bool:
        """Remove the sidecar of a record that is gone. Never waits for the store; checked again under its lock, so a
        strategy promoted again in the meantime keeps its sidecar. True when it was removed."""
        try:
            with store.write_lock(self._at, 0.0):
                if store.get(sname, self._at) is not None:
                    return False
                return store.remove_desk(sname, self._at)
        except Exception:  # noqa: BLE001 -- held, or it cannot be removed: the next refresh tries again
            return False

    async def refresh(self) -> dict | None:
        """Bring the config in line with the store. None when it was skipped: the views are paused (before the read,
        or by the time it came back), a request is writing, or the desk changed something while the read ran."""
        if self._paused():
            return None
        own = self.owner()
        if labcfg.any_busy(self.cfg):
            return None
        gen = self._gen
        snap, beat = await asyncio.to_thread(self._read)
        if gen != self._gen or self._paused() or labcfg.any_busy(self.cfg):
            return None
        out = labcfg.apply(self.cfg, snap, held=lambda did: bool(self._open(did)))
        try:
            seen = dt.datetime.fromisoformat((beat or {}).get("seen_utc"))
            self._seen_utc = seen if seen.tzinfo is not None else seen.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            self._seen_utc = None
        for did in out["added"]:
            self._journal("lab_added", strategy=did, mark=labcfg.mark_of(self.cfg, did))
        self._say_notes()
        # a record that is gone with no round open: its sidecar goes too (the owner's job), so the Lab page is never
        # left refusing Promote / Remove for a name that is no longer on the Desk
        dropped = {sname: self._drop_orphan(sname) for sname in labcfg.orphans(self.cfg, snap)} if own else {}
        for did in out["removed"]:
            self._journal("lab_removed", strategy=did, why="record gone",
                          sidecar_removed=dropped.pop(labcfg.store_name(did), False))
        for sname, ok in dropped.items():    # a sidecar left from before (the record went while the desk was down)
            if ok:
                self._journal("lab_removed", strategy=labcfg.desk_id(sname), why="record gone", sidecar_removed=True)
        if own and labcfg.pending(self.cfg):     # a dropped book, a cleaned row, a write the hook missed
            labcfg.persist_all(self.cfg, self._at)   # never waits: a miss is tried again by the next refresh
        return out

    async def run(self, interval_s: float = REFRESH_S) -> None:
        """The background task. An error is journaled (the same one once a minute at most) and never ends it."""
        while True:
            try:
                self.owner()
                await self.refresh()
            except Exception as e:  # noqa: BLE001 -- the next round tries again
                msg, now = str(e)[:200], time.monotonic()
                if self._said is None or self._said[0] != msg or now - self._said[1] >= 60.0:
                    self._said = (msg, now)
                    self._journal("lab_refresh_error", error=msg)
            await asyncio.sleep(interval_s)

    # ------------------------------------------------------------ write first, then remember
    async def _write(self, name: str, work, keep):
        """One change of one strategy: `work()` is the disk half (in a thread; it waits at most REQ_WAIT_S for the
        store), `keep(result)` the memory half (on the loop, only once the disk half is done). Refused "Could not save
        it. Try again." when the disk half fails or another change of this strategy is still being written; nothing has
        changed then. While it runs the refresh applies nothing and the after-save hook leaves this strategy alone. The
        pair is shielded: a request that is cancelled half-way still ends with memory and disk agreeing."""
        m = labcfg.entry(self.cfg, name)
        if m is None:
            raise Refused(NOT_ON_DESK, 404)
        if m["busy"]:
            raise Refused(NOT_SAVED)
        labcfg.set_busy(self.cfg, name, True)
        self._gen += 1

        async def both():
            try:
                try:
                    got = await asyncio.to_thread(work)
                except Exception as e:  # noqa: BLE001 -- the store is held, or the disk said no
                    self._journal("lab_save_error", strategy=name, error=f"{type(e).__name__}: {e}"[:200])
                    raise Refused(NOT_SAVED) from None
                return keep(got)
            finally:
                self._gen += 1
                labcfg.set_busy(self.cfg, name, False)
        task = asyncio.ensure_future(both())
        task.add_done_callback(lambda t: t.cancelled() or t.exception())     # a result nobody waits for any more
        return await asyncio.shield(task)

    async def _commit(self, name: str, limits, rows: list) -> None:
        """This strategy's limits and book: to its sidecar, then to the desk's memory."""
        cfg, at, sname = self.cfg, self._at, labcfg.store_name(name)
        m = labcfg.entry(cfg, name)
        if m["busy"]:                        # another change of this strategy is still being written
            raise Refused(NOT_SAVED)
        want = labcfg.sidecar(cfg, name, limits, rows)
        nothing = m["saved"] is None and want["limits"] is None and not want["book"]
        if want == m["saved"] or nothing or (m["frozen"] and limits is None):
            # nothing to write: the sidecar already says so, there is nothing to say, or it holds limits the desk
            # cannot read and is left as it is until he saves limits again
            labcfg.commit(cfg, name, limits, rows, None)
            return

        def work():
            with store.write_lock(at, REQ_WAIT_S):
                store.put_desk(sname, labcfg.stamped(want), at)
        await self._write(name, work, lambda _: labcfg.commit(cfg, name, limits, rows, want))

    # ------------------------------------------------------------ limits
    async def set_limits(self, name: str, body) -> dict:
        """ValueError: a bad field, with its sentence. Refused: not a Lab strategy (404), another desk owns the store,
        the 9:30 window, a round open, an account booked for more than the new cap, or the sidecar could not be
        written. Nothing changes on a refusal."""
        self._need(name)
        self._must_own()
        limits = labcfg.parse_limits(body, labcfg.record_of(self.cfg, name))
        if self._in_quiet():
            raise Refused(NOT_NOW)
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        rows = [dict(r) for r in self.cfg.book.get(name) or []]
        if any(int(r.get("qty") or 0) > limits.max_qty for r in rows):
            raise Refused(BOOKED_FOR_MORE)
        was = labcfg.limits_of(self.cfg, name)
        await self._commit(name, limits, rows)
        self._journal("lab_limits_set", strategy=name, limits=asdict(limits), previous=asdict(was) if was else None)
        return {"ok": True, "strategy": name, "limits": asdict(limits)}

    # ------------------------------------------------------------ the book
    def check_book(self, name: str, rows: list) -> None:
        """Before a book write of ANY strategy: raises Refused with the sentence. `rows` is what the route will
        write ([{account, qty}], sizes above 0). With no Lab strategy on the desk it says nothing."""
        if not labcfg.lab_ids(self.cfg):
            return
        s = self.cfg.strategies.get(name)
        if s is None:
            return
        mine = self.is_lab(name)
        if mine:
            limits = labcfg.limits_of(self.cfg, name)
            if rows and limits is None:
                raise Refused(SET_LIMITS_FIRST)
            for r in rows:
                if int(r["qty"]) > limits.max_qty:
                    raise Refused(f"Size is capped at {limits.max_qty} here.")
            seen: dict = {}
            for r in rows:                   # one broker account once (two desk entries can be pinned to one)
                key = getattr(self.adapters.get(r["account"]), "broker_key", r["account"])
                if key in seen:
                    raise Refused(f"That is the same broker account as {self._label(seen[key])}.")
                seen[key] = r["account"]
        for r in rows:                       # one strategy per market per account (the engine's substring rule)
            for other, so in self.cfg.strategies.items():
                if other == name or not (mine or getattr(so, "kind", "") == LAB):
                    continue
                a, b = str(s.symbol).upper(), str(so.symbol).upper()
                if not a or not b or not (a in b or b in a):
                    continue
                if any(x.get("account") == r["account"] for x in assignments(self.cfg, other)):
                    raise Refused(f"Another strategy trades {so.symbol} on this account.")
        if mine:
            keep = {r["account"] for r in rows}
            if any(aid not in keep for aid in self._open(name)):
                raise Refused(FLATTEN_FIRST)

    async def set_book(self, name: str, rows: list) -> None:
        """A Lab strategy's book (it lives in its sidecar, never in config.json): the checks, then the file, then the
        desk's memory. Refused with the sentence; nothing changes then."""
        self._need(name)
        self._must_own()
        self.check_book(name, rows)
        await self._commit(name, labcfg.limits_of(self.cfg, name), [{"account": r["account"], "qty": int(r["qty"])} for r in rows])

    # ------------------------------------------------------------ the switch
    async def set_enabled(self, name: str, on: bool) -> bool:
        """Write the store record's `enabled`. Switching ON needs the promotion the desk knows (False: the record was
        promoted again, or is gone -- the page says "The Lab record changed. Try again.") and a record the desk can
        read. Switching OFF is never refused for the record: off is off whatever it now is. Refused when another desk
        owns the store or the record could not be written (nothing changes)."""
        if not self.is_lab(name):
            return False
        self._must_own()
        on = bool(on)
        if on and labcfg.unreadable(self.cfg, name):
            raise Refused(CANNOT_READ)
        cfg, at, sname, mark = self.cfg, self._at, labcfg.store_name(name), labcfg.mark_of(self.cfg, name)

        def keep(rec) -> bool:
            if rec is None and on:
                return False
            labcfg.set_enabled(cfg, name, on)
            return True
        return await self._write(name, lambda: store.set_enabled(sname, on, at, mark if on else None, wait_s=REQ_WAIT_S), keep)

    # ------------------------------------------------------------ remove
    async def remove(self, name: str) -> dict:
        self._need(name)
        self._must_own()
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        cfg, at, sname = self.cfg, self._at, labcfg.store_name(name)
        accounts = [r["account"] for r in assignments(cfg, name)]

        began = []

        def work():
            with store.write_lock(at, REQ_WAIT_S):
                began.append(True)
                store.remove_desk(sname, at)
                store.remove(sname, at)
        try:
            await self._write(name, work, lambda _: labcfg.forget(cfg, name))
        except Refused:
            m = labcfg.entry(cfg, name)
            if began and m is not None and m["saved"] is not None:
                m["saved"] = {"unknown": True}       # it stopped half-way: the sidecar may be gone, so the next
            raise                                    # refresh writes it again from what the desk holds
        self._journal("lab_removed", strategy=name, why="removed", unbooked=accounts)
        return {"ok": True, "removed": name}

    # ------------------------------------------------------------ the status block
    def _runner(self) -> dict:
        if self._seen_utc is None:
            return {"alive": False, "age_s": None}
        age = abs((dt.datetime.now(dt.timezone.utc) - self._seen_utc).total_seconds())
        return {"alive": age <= RUNNER_ALIVE_S, "age_s": round(age, 1)}

    def _rounds(self, name: str) -> list:
        """Today's rounds, oldest first. engine.lab_rounds (task B2) is asked when it is there; until then each
        account's one day state is its round 1."""
        ask = getattr(self.engine, "lab_rounds", None)
        rows = ask(name) if ask is not None else [{**vars(st), "round": 1, "why": st.note or None}
                                                  for st in self.engine.day_states(name)]
        return [{"account": r.get("account"), "round": r.get("round"), "status": r.get("status"),
                 "side": r.get("side", r.get("entry_side")), "qty": r.get("qty"), "entry_fill": r.get("entry_fill"),
                 "exit_fill": r.get("exit_fill"), "exit_reason": r.get("exit_reason"), "pnl": r.get("pnl"),
                 "why": r.get("why")} for r in rows]

    def _state(self, name: str) -> tuple:
        """(state, why) from what the desk itself knows. The runner's states (watching, runner_down, done for today)
        come with the intake half."""
        if labcfg.unreadable(self.cfg, name):
            return "check", CANNOT_READ
        if labcfg.frozen(self.cfg, name):
            return "check", CANNOT_READ_LIMITS
        s = self.cfg.strategies[name]
        day = self.engine.day_status(name)
        if day == "error":
            return "check", None
        if day == "live":
            return "in_position", None
        if day in ("placing", "placed"):
            return "working", None
        if not s.enabled:
            return "off", None
        if not assignments(self.cfg, name):
            return "shadow", None
        if self.engine.killed_today(name):
            return "stopped", "Killed today."
        if not self.cfg.armed:
            return "disarmed", None
        return "waiting", None

    def status_view(self, name: str) -> dict | None:
        """The `lab` block of /api/status; None for a strategy that is not from the Lab. Memory only, and it never
        raises: the whole Desk page reads through this route."""
        if not self.is_lab(name):
            return None
        sname = labcfg.store_name(name)
        try:
            limits = labcfg.limits_of(self.cfg, name)
            state, why = self._state(name)
            return {"name": sname, "mark": labcfg.mark_of(self.cfg, name), "limits": asdict(limits) if limits else None,
                    "state": state, "why": why,
                    "trades_today": 0, "mode_today": None,           # the intake half (B3) fills these
                    "runner": self._runner(), "rounds": self._rounds(name),
                    "refused": []}                                   # ... and this
        except Exception as e:  # noqa: BLE001 -- the page gets the plain sentence, the journal the detail (once)
            key = (name, f"{type(e).__name__}: {e}"[:200])
            if key not in self._said_view and len(self._said_view) < 100:
                self._said_view.add(key)
                self._journal("lab_view_error", strategy=name, error=key[1])
            return {"name": sname, "mark": None, "limits": None, "state": "check", "why": CANNOT_READ,
                    "trades_today": 0, "mode_today": None, "runner": {"alive": False, "age_s": None}, "rounds": [], "refused": []}
