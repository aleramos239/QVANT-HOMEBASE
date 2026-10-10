"""The desk's side of a promoted Lab strategy (Step B). This file is the CONFIG half (task B1): the desk knows the
strategy, keeps its limits and its book, switches it, removes it and says what it is doing. The INTAKE half (task B3:
the runner's orders, the stream, the heartbeat rule) is added to this class later; until then nothing here, and nothing
that calls it, can send an order.

THE LAB SIDE IS OPT-IN PER DESK. server.create_app(..., lab=None) turns it on only when the file

    <state_dir>/lab_desk.on            (homebase/.state/lab_desk.on of the checkout the desk runs from; any content)

exists: flagged(state_dir()), read once, when the app is built. state_dir is per checkout, so a desk run from another
worktree or a copy never has it. The lead creates the file once, in the live checkout, at go-live (and removes it to
switch the Lab side off at the next desk start). Tests pass lab=True / lab=False. With the Lab side OFF (LabDesk(...,
on=False), attach() never called) the desk never reads the store, never tries its lock, overlays no Lab strategy, has no
`lab` key in its status, and answers the two Lab routes with "Lab strategies are switched off on this Desk.".

    attach(cfg)            the desk's start: overlay the promoted strategies on the config, register the sidecar writer
                           as config.save's after-save hook. Never raises: a Lab problem never stops the desk.
    LabDesk.owner()        ONE desk owns a store (labcfg.take_store: <store>/desk.lock) -- the second line of defence
                           for two flagged desks. The lock is taken ONLY inside refresh(), which then re-reads every
                           sidecar in the same pass; a desk that holds the lock but still owes that re-read is not the
                           owner yet and writes nothing. A desk that is not the owner reads only: it writes no sidecar,
                           follows the owner's, and refuses limits, book, switching ON and Remove (switching OFF is
                           never refused). It asks again on every refresh.
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

FLAG_FILE = "lab_desk.on"                # in the checkout's state folder: this desk's Lab side is on (see the top)
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
READ_ONLY_HERE = "Another Desk is running on this store: Lab strategies are read-only here."
CANNOT_READ = "The Desk cannot read it."
CANNOT_READ_LIMITS = "The Desk cannot read its limits."
SWITCH_NOT_OFF = "Flattened. Could not switch it off: try the switch again."
SWITCHED_OFF = "Lab strategies are switched off on this Desk."


class Refused(Exception):
    """A request the desk will not take. str(e) is the sentence the page shows; `status` is the HTTP status."""

    def __init__(self, sentence: str, status: int = 409):
        super().__init__(sentence)
        self.status = status


def flagged(state_dir) -> bool:
    """Is this desk's Lab side switched on? The ONE place the flag is read: the file <state_dir>/lab_desk.on exists.
    Anything that goes wrong reading it means off."""
    try:
        return (state_dir / FLAG_FILE).is_file()
    except Exception:  # noqa: BLE001
        return False


def readiness_line(cfg: AppCfg) -> dict | None:
    """The one readiness line of a desk that reads only (another desk holds the store), when there is a Lab strategy
    to be read-only about. None for every other desk. Memory only."""
    try:
        if labcfg.store_state(cfg) == "busy" and labcfg.lab_ids(cfg):
            return {"level": "warn", "label": "Lab strategies", "detail": READ_ONLY_HERE}
    except Exception:  # noqa: BLE001 -- readiness is the whole desk's: a Lab problem adds no line, never breaks it
        pass
    return None


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
    def __init__(self, cfg: AppCfg, engine, adapters: dict, *, paused: Callable[[], bool] | None = None, at=None,
                 on: bool = True):
        self.cfg, self.engine, self.adapters = cfg, engine, adapters
        self.on = bool(on)               # False: this desk's Lab side is switched off -- every method is inert
        self._paused = paused or (lambda: False)
        if at is not None and self.on:
            labcfg.bind(cfg, at)
        self._at = cfg.__dict__.get("_lab_at")
        self._gen = 0                    # bumped by every change the desk itself makes: a store read that began
                                         # before one is thrown away (it may hold what the change replaced)
        self._seen_utc: dt.datetime | None = None    # the runner's heartbeat, as last read
        self._said: tuple | None = None  # (error text, monotonic) of the last lab_refresh_error line
        self._said_busy = False          # lab_store_busy / lab_store_error are journaled once each
        self._said_err = False
        self._said_view: set = set()     # (strategy, error) of the lab_view_error lines

    # ------------------------------------------------------------ one desk owns the store
    def owner(self) -> bool:
        """True for the one desk that may write this store's sidecars: it holds the lock AND has re-read every sidecar
        since it took it. Asking never takes the lock: only refresh() does."""
        return self.on and labcfg.ready(self.cfg)

    def _try_store(self) -> None:
        """Inside refresh() only, right before the read that will re-read every sidecar: take the store if nobody
        holds it. A desk that does not get it -- another desk holds it, or the lock could not be tried -- says so
        once and asks again on the next refresh."""
        if labcfg.owns(self.cfg):
            return
        labcfg.take_store(self.cfg, self._at)
        state = labcfg.store_state(self.cfg)
        if state == "busy" and not self._said_busy:
            self._said_busy = True
            self._journal("lab_store_busy", store=str(store.root(self._at)))
        elif state == "unknown" and not self._said_err:
            self._said_err = True
            self._journal("lab_store_error", store=str(store.root(self._at)), error=labcfg.store_error(self.cfg))

    def close(self) -> None:
        """Give the store back (the desk is shutting down; the OS does the same when the process ends)."""
        if self.on:
            labcfg.release_store(self.cfg)

    def _must_own(self) -> None:
        """For limits, the book, switching ON and Remove. Nothing here takes the store: a desk becomes the owner only
        in a refresh, which re-reads every sidecar under its own lock first. Until then the answer is a refusal --
        "Another Desk is running on this store." while another desk holds it or the take-over's re-read is still owed."""
        if not self.on:
            raise Refused(SWITCHED_OFF)
        if labcfg.ready(self.cfg):
            return
        raise Refused(OTHER_DESK if labcfg.store_state(self.cfg) == "busy" or labcfg.owns(self.cfg) else NOT_SAVED)

    def _read_only(self) -> bool:
        """What the status block says: this desk cannot change a Lab strategy now (another desk holds the store, the
        lock could not be tried, or the take-over's re-read is still owed). A desk that never asked says nothing."""
        return labcfg.store_state(self.cfg) in ("busy", "unknown") or (labcfg.owns(self.cfg) and not labcfg.ready(self.cfg))

    # ------------------------------------------------------------ small reads (memory only)
    def is_lab(self, name) -> bool:
        s = self.cfg.strategies.get(name)
        return self.on and s is not None and getattr(s, "kind", "") == LAB and labcfg.is_lab(self.cfg, name)

    def book_view(self) -> dict:
        """The book as /api/status shows it. For a Lab strategy only the rows of accounts in this desk's pool: the page
        must never see, or send back, a row it cannot act on (the others stay in cfg.book and in the sidecar). Every
        other strategy's rows as they are; with the Lab side off, cfg.book itself."""
        if not self.on or not labcfg.lab_ids(self.cfg):
            return self.cfg.book
        return {name: ([r for r in rows if r.get("account") in self.cfg.accounts] if labcfg.is_lab(self.cfg, name) else rows)
                for name, rows in self.cfg.book.items()}

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

    def _say_notes(self, dropped: dict) -> None:
        """Journal what the overlay had to say (labcfg.take_notes). A desk that reads only dropped nothing on disk:
        its `lab_unbooked` notes are about its own view and are not journaled, and its `lab_removed` lines name no
        accounts. `dropped`: the sidecars this refresh removed ({store name: removed})."""
        own = labcfg.ready(self.cfg)
        for event, fields in labcfg.take_notes(self.cfg):
            if event == "lab_unbooked" and not own:
                continue
            if event == "lab_removed":
                fields = {**fields, "sidecar_removed": dropped.pop(labcfg.store_name(fields.get("strategy")), False)}
                if not own:
                    fields.pop("unbooked", None)
            self._journal(event, **fields)

    # ------------------------------------------------------------ the 2 s refresh
    def _read(self) -> tuple:
        """The disk half, in a thread: every record with its sidecar, and the runner's heartbeat."""
        return labcfg.read_store(self._at), store.get_runner(self._at)

    def _drop_orphan(self, sname: str) -> bool:
        """Remove the sidecar of a record whose FILE is gone. Never waits for the store; checked again under its lock,
        so a strategy promoted again in the meantime -- or a record file that is there, readable or not -- keeps its
        sidecar. True when it was removed."""
        try:
            with store.write_lock(self._at, 0.0):
                if not labcfg.owns(self.cfg) or store.has_record_file(sname, self._at):
                    return False
                return store.remove_desk(sname, self._at)
        except Exception:  # noqa: BLE001 -- held, or it cannot be removed: the next refresh tries again
            return False

    async def refresh(self) -> dict | None:
        """Bring the config in line with the store. None when it was skipped: the views are paused (before the read,
        or by the time it came back), a request is writing, or the desk changed something while the read ran."""
        if not self.on or self._paused():
            return None
        if labcfg.any_busy(self.cfg):
            return None
        self._try_store()                    # the ONLY place the store is taken: right before the read below, so the
        gen = self._gen                      # sidecars are re-read under this desk's own lock in the same pass
        snap, beat = await asyncio.to_thread(self._read)
        if gen != self._gen or self._paused() or labcfg.any_busy(self.cfg):
            return None                      # (a store taken above stays taken; its re-read is still owed)
        taking = labcfg.owns(self.cfg) and not labcfg.ready(self.cfg)
        if taking:                           # what it noted while it did not own the store was about its own view:
            labcfg.drop_notes(self.cfg, "lab_unbooked")      # the re-read says again, for the journal, what really goes
        held = lambda did: bool(self._open(did))  # noqa: E731
        # a reader follows the owner's sidecars; the pass that makes this desk the owner re-reads EVERY one of them
        out = labcfg.apply(self.cfg, snap, held=held, reload=not labcfg.ready(self.cfg))
        own = labcfg.ready(self.cfg)
        if taking and own and (self._said_busy or self._said_err):
            self._journal("lab_store_owned", store=str(store.root(self._at)))
            self._said_busy = self._said_err = False
        try:
            seen = dt.datetime.fromisoformat((beat or {}).get("seen_utc"))
            self._seen_utc = seen if seen.tzinfo is not None else seen.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            self._seen_utc = None
        for did in out["added"]:
            self._journal("lab_added", strategy=did, mark=labcfg.mark_of(self.cfg, did))
        # a record whose FILE is gone with no round open: its sidecar goes too (the owner's job), so the Lab page is
        # never left refusing Promote / Remove for a name that is no longer on the Desk
        dropped = {sname: self._drop_orphan(sname) for sname in labcfg.orphans(self.cfg, snap, held)} if own else {}
        self._say_notes(dropped)             # `lab_removed` lines carry the accounts and whether the sidecar went
        for sname, ok in dropped.items():    # a sidecar left from before (the record went while the desk was down)
            if ok:
                self._journal("lab_removed", strategy=labcfg.desk_id(sname), why="record gone", sidecar_removed=True)
        if own and labcfg.pending(self.cfg):     # a dropped book, a cleaned row, a write the hook missed
            try:
                labcfg.persist_all(self.cfg, self._at)   # never waits for the store ...
            except TimeoutError:
                pass                         # ... and a miss is not an error: the next refresh tries again
        return out

    async def run(self, interval_s: float = REFRESH_S) -> None:
        """The background task. An error is journaled (the same one once a minute at most) and never ends it."""
        if not self.on:
            return
        while True:
            try:
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
            # cannot read (or the file itself does not read) and is left as it is until he saves limits again
            labcfg.commit(cfg, name, limits, rows, None)
            return
        never_read = labcfg.blind(cfg, name)

        def work():
            with store.write_lock(at, REQ_WAIT_S):
                self._still_mine()
                store.put_desk(sname, labcfg.stamped(want), at)

        def keep(_):
            labcfg.commit(cfg, name, limits, rows, want)
            labcfg.strip_removed(cfg, name)  # an account that left the desk while this was being written stays out
        await self._write(name, work, keep)
        if never_read:                       # he saved limits over a sidecar file the desk could not read
            self._journal("lab_sidecar_replaced", strategy=name)

    def _still_mine(self) -> None:
        """In a writer's thread, under the store's write lock: the desk may have let the store go (it is shutting
        down) while this write waited its turn. Then nothing is written."""
        if not labcfg.owns(self.cfg):
            raise RuntimeError("the desk no longer holds the store")

    # ------------------------------------------------------------ limits
    async def set_limits(self, name: str, body) -> dict:
        """ValueError: a bad field, with its sentence. Refused: the Lab side is off, not a Lab strategy (404), another
        desk owns the store, the 9:30 window, a round open, an account booked for more than the new cap, or the
        sidecar could not be written. Nothing changes on a refusal."""
        if not self.on:
            raise Refused(SWITCHED_OFF)
        self._need(name)
        self._must_own()
        limits = labcfg.parse_limits(body, labcfg.record_of(self.cfg, name))
        if self._in_quiet():
            raise Refused(NOT_NOW)
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        if any(int(r.get("qty") or 0) > limits.max_qty for r in assignments(self.cfg, name)):
            raise Refused(BOOKED_FOR_MORE)   # (the rows of accounts this desk has; another pool's are not its to judge)
        rows = [dict(r) for r in self.cfg.book.get(name) or []]
        was = labcfg.limits_of(self.cfg, name)
        await self._commit(name, limits, rows)
        self._journal("lab_limits_set", strategy=name, limits=asdict(limits), previous=asdict(was) if was else None)
        return {"ok": True, "strategy": name, "limits": asdict(limits)}

    # ------------------------------------------------------------ the book
    def check_book(self, name: str, rows: list) -> None:
        """Before a book write of ANY strategy: raises Refused with the sentence. `rows` is what the route will
        write ([{account, qty}], sizes above 0). With no Lab strategy on the desk it says nothing."""
        if not self.on or not labcfg.lab_ids(self.cfg):
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
        desk's memory. `rows` are the new rows FOR THIS DESK'S POOL; the rows of accounts that are not in the pool are
        kept as they are, unposted. Refused with the sentence; nothing changes then."""
        if not self.on:
            raise Refused(SWITCHED_OFF)
        self._need(name)
        self._must_own()
        self.check_book(name, rows)
        # the rows of accounts that are not in this desk's pool are not its to take off: they stay as they are
        others = [dict(r) for r in self.cfg.book.get(name) or [] if r.get("account") not in self.cfg.accounts]
        await self._commit(name, labcfg.limits_of(self.cfg, name),
                           [{"account": r["account"], "qty": int(r["qty"])} for r in rows] + others)

    # ------------------------------------------------------------ the switch
    async def set_enabled(self, name: str, on: bool) -> bool:
        """Write the store record's `enabled`. Switching ON needs the store (a desk that reads only refuses), the
        promotion the desk knows (False: the record was promoted again, or is gone -- the page says "The Lab record
        changed. Try again.") and a record the desk can read. Switching OFF is NEVER refused: not on a desk that reads
        only, not for a changed record -- the switch is the record's, and refusing OFF protects nothing. Either way
        "Could not save it. Try again." when the record could not be written (nothing changes)."""
        if not self.is_lab(name):
            return False
        on = bool(on)
        if on:
            self._must_own()
            if labcfg.unreadable(self.cfg, name):
                raise Refused(CANNOT_READ)
        cfg, at, sname, mark = self.cfg, self._at, labcfg.store_name(name), labcfg.mark_of(self.cfg, name)

        def keep(rec) -> bool:
            if rec is None and on:
                return False
            labcfg.set_enabled(cfg, name, on)
            return True
        return await self._write(name, lambda: store.set_enabled(sname, on, at, mark if on else None, wait_s=REQ_WAIT_S), keep)

    # ------------------------------------------------------------ remove
    async def _remove_unusable(self, name: str) -> dict:
        """A store name whose record FILE is there but FAILS to load as a strategy (it does not read, or names no
        market): its sidecar and its record go, the history stays. So a record the Lab page refuses to touch ("Take its
        accounts off on the Desk first.") always has a way out here. A GOOD record this desk simply has not read yet
        (promoted a moment ago) is not one of these: it is refused, and is removed the usual way once it is on the Desk."""
        sname = labcfg.store_name(name)
        try:
            store.has_record_file(sname, self._at)       # (also: is it a name the store takes at all?)
        except (ValueError, TypeError):
            raise Refused(NOT_ON_DESK, 404) from None
        self._must_own()
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        at = self._at

        def work():
            with store.write_lock(at, REQ_WAIT_S):
                self._still_mine()
                if not store.has_record_file(sname, at):
                    return None
                rec = store.get(sname, at)
                try:
                    good = rec is not None and rec.get("name") == sname and labcfg.usable(rec) \
                        and labcfg.strategy_cfg(rec, None) is not None
                except Exception:  # noqa: BLE001 -- it cannot be made a strategy: that is what "unusable" means
                    good = False
                if good:
                    return None
                side = store.get_desk(sname, at)
                held = [r.get("account") for r in (side or {}).get("book") or [] if isinstance(r, dict)] \
                    if isinstance(side, dict) else []
                store.remove_desk(sname, at)
                store.remove(sname, at)
                return held
        self._gen += 1
        try:
            held = await asyncio.shield(asyncio.to_thread(work))
        except Exception as e:  # noqa: BLE001
            self._journal("lab_save_error", strategy=name, error=f"{type(e).__name__}: {e}"[:200])
            raise Refused(NOT_SAVED) from None
        finally:
            self._gen += 1
        if held is None:
            raise Refused(NOT_ON_DESK, 404)
        self._journal("lab_removed", strategy=name, why="removed", unusable=True, unbooked=held)
        return {"ok": True, "removed": name}

    async def remove(self, name: str) -> dict:
        if not self.on:
            raise Refused(SWITCHED_OFF)
        if not self.is_lab(name) and labcfg.store_name(name) is not None and name not in self.cfg.strategies:
            return await self._remove_unusable(name)
        self._need(name)
        self._must_own()
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        cfg, at, sname = self.cfg, self._at, labcfg.store_name(name)
        accounts = [r.get("account") for r in cfg.book.get(name) or []]      # every row goes with the sidecar

        began = []

        def work():
            with store.write_lock(at, REQ_WAIT_S):
                self._still_mine()
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
                    "refused": [],                                   # ... and this
                    "read_only": self._read_only()}                  # another desk owns the store
        except Exception as e:  # noqa: BLE001 -- the page gets the plain sentence, the journal the detail (once)
            key = (name, f"{type(e).__name__}: {e}"[:200])
            if key not in self._said_view and len(self._said_view) < 100:
                self._said_view.add(key)
                self._journal("lab_view_error", strategy=name, error=key[1])
            return {"name": sname, "mark": None, "limits": None, "state": "check", "why": CANNOT_READ,
                    "trades_today": 0, "mode_today": None, "runner": {"alive": False, "age_s": None}, "rounds": [], "refused": [],
                    "read_only": self._read_only()}
