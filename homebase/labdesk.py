"""The desk's side of a promoted Lab strategy (Step B). The CONFIG half (task B1) comes first: the desk knows the
strategy, keeps its limits and its book, switches it, removes it and says what it is doing; nothing in it can send an
order. The INTAKE half (task B3, from "THE INTAKE HALF" on: LabDesk.event, heartbeat, snapshot, subscribe, stop, the
start lines) is the ONE door through which the runner's orders reach the engine: read its own header before changing it.

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
import json
import logging
import re
import sys
import time
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass
from typing import Callable

from . import config as config_mod
from . import labcfg
from .config import AppCfg, assignments
from .contracts import point_value, tick_size
from .labcfg import LAB
from .labrun import door, fanout, intents, store

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

# ---- the intake half (task B3): the runner's orders, the heartbeat rule, the stream back (see THE INTAKE HALF below)
RATE_N, RATE_WINDOW_S = 5, 1.0           # entries: at most this many requests a second per strategy (trading.py's own)
MAX_ORDERS = 20                          # order intents in one event (the host's own limit)
PRICE_FRESH_S, PRICE_AHEAD_S = 30.0, 5.0     # the runner's last print: at most this old / this far ahead of the desk clock
HOLD_S, HOLD_POLL_S = 2.0, 0.02          # an entry waits this long, at most, for the 9:30 orders to go first
FIRE_LEAD_S, FIRE_AFTER_S = 2.0, 0.5     # ... "near a fire": from this long before a timer strategy's fire to just after
PUBLISH_S = 0.25                         # the stream's snapshots are compared this often
SUB_QUEUE_MAX = 200                      # snapshots a stream reader may fall behind before it is dropped
ANSWERS_KEPT = 2000                      # answered events kept per strategy per day (an older `seq` is out of date)
REFUSED_KEPT = 20                        # refusals shown on the Desk page
DEAD_KEPT = 200                          # order ids no account took, kept for the snapshot (the newest)
GHOST_SAY_S = 60.0                       # a name that is not a Lab strategy here: one `lab_refused` line this often

# The sentences the intake answers (design C3 and E). The engine's and the door's are repeated here so this module
# never imports the engine (its imports reach the tester's tape); tests/test_labdesk.py holds them equal.
OFF = "It is off."
KILLED = "Killed today."
STOPPED_TODAY = "Stopped for today."
OUT_OF_DATE = "This order is out of date."
TOO_MANY = "Too many orders at once."
FIRE_FIRST = "The 9:30 orders go first."
PRICE_PAST = "The price is already past this entry."
LAST_TRADE = "The Desk cannot check the last trade's orders."     # the engine's own (LAB_CANNOT_CHECK)
BOTH_FILLED = "Both entries filled."     # why the desk stops a strategy whose pair filled on both sides
TAKE_RULE = "This account has a daily take rule. A Lab strategy cannot share it."
NOT_WRITTEN = "The Desk could not write this trade down. Nothing was sent."
BROKER_REFUSED = "The broker refused it: "
OPEN_WITHOUT_CFG = "A Lab trade is open but its strategy is not on this Desk. Check it."
NOT_READ = "The request does not read."
PLACING_UNKNOWN = "placement outcome unknown after a restart — check the broker"     # the engine's own note
EXITS = ("cancel", "flatten", "stop")    # always applied, in every desk state
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        self._intake_init()              # the intake half (task B3, below): its own fields, nothing read or sent

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

    async def run(self, interval_s: float = REFRESH_S, publish_s: float = PUBLISH_S) -> None:
        """The background task. Every interval_s: the refresh, then one Lab call per strategy (_lab_calls: the
        engine's day roll and carry happen only at a Lab call -- also on a pass whose disk part was skipped for a view
        pause). Every publish_s: the heartbeat rule and the stream's snapshots (_intake_tick). An error is journaled
        (the same one once a minute at most) and never ends it."""
        if not self.on:
            return
        due = 0.0
        self._lab_calls()                    # once at the start, before the first fill can arrive
        while True:
            now = time.monotonic()
            if now >= due:
                due = now + interval_s
                try:
                    await self.refresh()
                except Exception as e:  # noqa: BLE001 -- the next round tries again
                    msg, now = str(e)[:200], time.monotonic()
                    if self._said is None or self._said[0] != msg or now - self._said[1] >= 60.0:
                        self._said = (msg, now)
                        self._journal("lab_refresh_error", error=msg)
                self._lab_calls()
            await self._intake_tick()
            await asyncio.sleep(min(interval_s, publish_s))

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
            rules_for = getattr(self.engine, "rules_for", None)
            for r in rows:                   # ruling B2 Q-B: the engine's own notion (lab_enter sits such an account out)
                rules = rules_for(r["account"]) if rules_for is not None else None
                if rules is not None and (rules.day_take or rules.target_take):
                    raise Refused(TAKE_RULE)
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
        account's one day state is its round 1. An engine row also carries `carried` (True: a block from an earlier
        day, not one of today's trades -- the page shows it apart, with Clear) and `date` (the day it is from)."""
        ask = getattr(self.engine, "lab_rounds", None)
        rows = ask(name) if ask is not None else [{**vars(st), "round": 1, "why": st.note or None}
                                                  for st in self.engine.day_states(name)]
        return [{"account": r.get("account"), "round": r.get("round"), "status": r.get("status"),
                 "side": r.get("side", r.get("entry_side")), "qty": r.get("qty"), "entry_fill": r.get("entry_fill"),
                 "exit_fill": r.get("exit_fill"), "exit_reason": r.get("exit_reason"), "pnl": r.get("pnl"),
                 "why": r.get("why"),
                 **({"carried": bool(r["carried"]), "date": r.get("date")} if "carried" in r else {})} for r in rows]

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
            took = self._intake_view(name, state, why)               # the intake half (B3): what only it can tell
            return {"name": sname, "mark": labcfg.mark_of(self.cfg, name), "limits": asdict(limits) if limits else None,
                    "state": took["state"], "why": took["why"],
                    "trades_today": took["trades_today"], "mode_today": took["mode_today"],
                    "runner": self._runner(), "rounds": self._rounds(name),
                    "refused": took["refused"],
                    "read_only": self._read_only()}                  # another desk owns the store
        except Exception as e:  # noqa: BLE001 -- the page gets the plain sentence, the journal the detail (once)
            key = (name, f"{type(e).__name__}: {e}"[:200])
            if key not in self._said_view and len(self._said_view) < 100:
                self._said_view.add(key)
                self._journal("lab_view_error", strategy=name, error=key[1])
            return {"name": sname, "mark": None, "limits": None, "state": "check", "why": CANNOT_READ,
                    "trades_today": 0, "mode_today": None, "runner": {"alive": False, "age_s": None}, "rounds": [], "refused": [],
                    "read_only": self._read_only()}

    # ==================================================================================================================
    # THE INTAKE HALF (Step B, task B3): the ONE door through which a promoted strategy's orders reach the engine.
    #
    # The runner (a separate process) hosts the strategy's code and posts what it asks for, one EVENT at a time
    # (design C2): entries, a pair's link, cancels, a flatten, and its own `stop`. event() is the whole path:
    #
    #   ENTRIES need everything: the Lab side on, this desk owning the store (labcfg.ready), the strategy known and of
    #   kind lab, the order's mark equal to the record's and the sidecar's, its date the desk's, the strategy switched
    #   on, not killed today, not stopped today, limits set, an account booked; then the door (labrun.door, once per
    #   booked account with that account's size, on the state BEFORE the event), the size cap, a stop trigger the
    #   market has not passed, and the 9:30 orders going first. What is left goes to engine.lab_enter, which reads
    #   each account's position and asks every one of its own preconditions again before the order leaves.
    #
    #   EXITS (cancel, flatten, stop) need none of that: they are applied in every desk state.
    #
    # What the desk counts per strategy per day (trades a day, entries no account took, the answered `seq`, stopped)
    # is memory, written to the journal with every event and rebuilt from today's lines at the start (start()).
    # Nothing here is called by the engine: an error in this half can never reach its clock or another strategy.
    # ==================================================================================================================
    def _intake_init(self) -> None:
        self._mono = time.monotonic      # the rate limit's, the hold's and the heartbeat rule's clock (tests replace it)
        self._sleep = asyncio.sleep      # the hold's poll wait (tests replace it)
        self._t0 = self._mono()          # the desk's start: the heartbeat rule counts from here
        self._days: dict = {}            # strategy -> today's intake record (_rec)
        self._live: dict = {}            # strategy -> {"beat": monotonic | None, "info": the runner's words, "down": bool}
        self._hits: dict = {}            # strategy -> recent entry-carrying requests (the rate limit)
        self._locks: dict = {}           # strategy -> (loop, asyncio.Lock): one event of a strategy at a time
        self._subs: set = set()          # the stream's readers (bounded queues)
        self._last: dict = {}            # strategy -> the snapshot the readers were last sent
        self._said_tick: tuple | None = None     # (error text, monotonic) of the last lab_intake_error line
        self._orphans_said: set = set()  # (strategy, account) of the lab_open_without_cfg lines
        self._ghost_said: dict = {}      # a name that is not a Lab strategy here -> when its refusal was last journaled

    # ------------------------------------------------------------ small reads (memory only)
    def _lab_kind(self, name) -> bool:
        s = self.cfg.strategies.get(name)
        return s is not None and getattr(s, "kind", "") == LAB

    def _rec(self, name: str) -> dict:
        """Today's intake record of one Lab strategy. A new day starts a new one."""
        today = self.engine._today()
        d = self._days.get(name)
        if d is None or d["date"] != today:
            # answers: seq -> the stored answer; digest: seq -> the order intents of the event that got it (the same
            # seq with other intents is ANOTHER event: never answered from the store); both: the accounts whose
            # both-legs-filled round the desk already stopped the strategy for
            d = self._days[name] = {"date": today, "mark": None, "entries": 0, "untaken": 0, "stopped": None,
                                    "answers": OrderedDict(), "digest": {}, "seq_max": -1, "dead": [], "both": [],
                                    "refused": deque(maxlen=REFUSED_KEPT)}
        return d

    def _alive(self, name: str) -> dict:
        # fired: the open rounds (account, round, date) the heartbeat rule already cancelled the entries of
        return self._live.setdefault(name, {"beat": None, "info": None, "down": False, "fired": set()})

    @staticmethod
    def _keep(d: dict, seq: int, answer: dict, digest) -> None:
        """Store an event's answer under its seq, with the digest of its order intents. The FIRST answer of a seq is
        the one kept."""
        if seq in d["answers"]:
            return
        d["answers"][seq], d["digest"][seq] = answer, digest
        while len(d["answers"]) > ANSWERS_KEPT:
            d["digest"].pop(d["answers"].popitem(last=False)[0], None)

    @staticmethod
    def _dead(d: dict, ids) -> None:
        """Order ids no account took: the newest DEAD_KEPT."""
        d["dead"] += [i for i in ids if i not in d["dead"]]
        del d["dead"][:-DEAD_KEPT]

    def _lock(self, name: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        held = self._locks.get(name)
        if held is None or held[0] is not loop:
            held = self._locks[name] = (loop, asyncio.Lock())
        return held[1]

    def _rows(self, name: str) -> list:
        """engine.lab_rounds: today's rounds, oldest first (a block carried from an earlier day is a row too)."""
        ask = getattr(self.engine, "lab_rounds", None)
        return list(ask(name)) if ask is not None else []

    def _brain(self, name: str, rows: list | None = None) -> dict:
        """The one strategy brain (labrun.fanout) over today's rounds, plus the orders no account took: they have no
        round at all, and the strategy must still be told they are cancelled."""
        d = self._rec(name) if self.is_lab(name) else None
        b = fanout.brain(self._rows(name) if rows is None else rows, d["entries"] if d else 0)
        for i in (d["dead"] if d else ()):
            b["orders"].setdefault(str(i), {"status": "cancelled"})
        return b

    def _brain_now(self, name: str) -> dict | None:
        """The brain for an event's answer. One that cannot be built is None (the stream's next snapshot carries it):
        an event that was applied is always answered."""
        try:
            return self._brain(name)
        except Exception as e:  # noqa: BLE001
            self._say_tick(e)
            return None

    def _now_ms(self) -> int:
        return int(self.engine.now_et().timestamp() * 1000)

    # ------------------------------------------------------------ the 9:30 orders go first (ruling Q5)
    def held(self) -> bool:
        """A strategy that is not from the Lab is placing: its acks are out on this same loop. Nothing is published
        and no snapshot is built until they are in."""
        today = self.engine._today()
        return any(st.status == "placing" and st.date == today and not self._lab_kind(st.strategy)
                   for st in list(self.engine.states.values()))

    def _near_fire(self, now: dt.datetime) -> bool:
        """The seconds around a timer strategy's fire: from FIRE_LEAD_S before it to FIRE_AFTER_S after (by then its
        states read `placing`, which holds on its own). A timer strategy is what the two timers fire: an enabled,
        self-firing straddle or levels strategy that trades today (trading.ChartDesk._other_fire_near's notion, the
        09:30 fire included)."""
        if now.weekday() >= 5:
            return False
        from .timer import fire_time     # (here: importing this module must load nothing of the tester)
        secs = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        for s in list(self.cfg.strategies.values()):
            if not (s.enabled and getattr(s, "self_fire", False) and getattr(s, "kind", "straddle") in ("straddle", "levels")
                    and s.trades_on(now.date())):
                continue
            f = fire_time(s)
            fs = f.hour * 3600 + f.minute * 60 + f.second
            if fs - FIRE_LEAD_S <= secs < fs + FIRE_AFTER_S:
                return True
        return False

    def _fire_first(self) -> bool:
        return self.held() or self._near_fire(self.engine.now_et())

    async def _hold(self) -> tuple:
        """Before an entry leaves: wait while the 9:30 orders go first, HOLD_S at most. -> (go, it waited)."""
        end, waited = self._mono() + HOLD_S, False
        while self._fire_first():
            if self._mono() >= end:
                return False, waited
            waited = True
            await self._sleep(HOLD_POLL_S)
        return True, waited

    # ------------------------------------------------------------ what an entry needs (design C3, 1-2 and 6)
    def _stale(self, ev) -> str | None:
        """Checks 1 and 2, as one read with no side effect: the sentence that refuses this event's ENTRIES, or None.
        The strategy is on this Desk; this desk owns the store and has re-read it; the order was made for the
        promotion the desk knows (the record's mark AND the sidecar's) and for the desk's own day."""
        name = ev.strategy
        if not self.is_lab(name):
            return NOT_ON_DESK
        if not labcfg.ready(self.cfg):
            return OTHER_DESK if (labcfg.store_state(self.cfg) == "busy" or labcfg.owns(self.cfg)) else door.CANNOT_CHECK
        m = labcfg.entry(self.cfg, name)
        saved = m["saved"] if isinstance(m["saved"], dict) else {}
        mark = list(ev.mark)
        if mark != list(m["mark"]) or mark != saved.get("mark") or ev.date != self.engine._today():
            return OUT_OF_DATE
        return None

    def _not_now(self, name: str) -> str | None:
        """Check 6: off / killed today / stopped today / no limits."""
        s = self.cfg.strategies.get(name)
        if s is None or not s.enabled:
            return OFF
        if self.engine.killed_today(name):
            return KILLED
        if self._rec(name)["stopped"] is not None:
            return STOPPED_TODAY
        if labcfg.limits_of(self.cfg, name) is None:
            return CANNOT_READ_LIMITS if labcfg.frozen(self.cfg, name) else SET_LIMITS_FIRST
        return None

    def _too_fast(self, name) -> bool:
        """Check 3: at most RATE_N entry-carrying requests a second per strategy. `name` None: the one count every
        name that is not a Lab strategy on this Desk shares (nothing grows with the names a caller makes up)."""
        now = self._mono()
        hits = self._hits.setdefault(name, deque())
        while hits and now - hits[0] >= RATE_WINDOW_S:
            hits.popleft()
        if len(hits) >= RATE_N:
            return True
        hits.append(now)
        return False

    def _last_price(self, ev) -> float | None:
        """The runner's last print, when it is fresh by the DESK's clock; else None (and prices are late)."""
        if ev.last_ms is None or ev.last_price is None:
            return None
        age = self._now_ms() - ev.last_ms
        return ev.last_price if -PRICE_AHEAD_S * 1000 <= age <= PRICE_FRESH_S * 1000 else None

    @staticmethod
    def _past(it: dict, last: float | None) -> bool:
        """Ruling Q6: a stop entry whose trigger is already at or through the fresh last price. And (review I4) a
        market entry whose STOP the last price is already at or through: its bracket's stop would sit on the wrong
        side of the fill, so it is never sent."""
        if last is None:
            return False
        if it.get("kind") == "stop":
            return it["price"] - last <= 1e-9 if it["side"] == "long" else last - it["price"] <= 1e-9
        if it.get("kind") == "market" and it.get("sl") is not None:
            return last - it["sl"] <= 1e-9 if it["side"] == "long" else it["sl"] - last <= 1e-9
        return False

    def _verdicts(self, name: str, ev, booked: list) -> tuple:
        """Checks 7 and 8, once per booked account with that account's size: ({entry index: {account: sentence |
        None}}, {oco index: sentence | None}, {entry index: its pair's other index}). Judged against the state BEFORE
        the event, as the shadow host judges (host.py), so the owner reads the sentences he read in shadow."""
        d, limits, rec = self._rec(name), labcfg.limits_of(self.cfg, name), labcfg.record_of(self.cfg, name) or {}
        rows = self._rows(name)
        b = fanout.brain(rows, d["entries"])
        last, root = self._last_price(ev), rec.get("root")
        clean = all(r.get("clean") for r in rows if not r.get("carried"))
        # no position and nothing working, yet a round of today is not read ended: no account takes a new entry, and
        # the refusal says why in the engine's own words (the door only knows "not flat")
        unread = b["flat"] and not b["working"] and not clean
        state = {"flat": b["flat"] and clean,
                 "working_entries": b["working"], "entries_today": d["entries"], "last_price": last,
                 "now_hhmm": self.engine.now_et().strftime("%H:%M"), "prices_late": bool(ev.prices_late) or last is None}
        lim = {"max_trades_day": limits.max_trades_day, "max_qty": limits.max_qty, "max_risk_usd": limits.max_risk_usd,
               "last_entry_et": limits.last_entry_et, "session_from_et": labcfg.window(rec)[0],
               "point_value": point_value(root) if root else None, "tick": tick_size(root) if root else None}
        entries = [i for i, it in enumerate(ev.intents) if it["op"] == "entry"]
        index = {ev.intents[i]["id"]: i for i in entries}
        per: dict = {i: {} for i in entries}
        oco: dict = {}
        pair: dict = {}
        for row in booked:
            a, q = row["account"], int(row["qty"])
            got = door.check_event([dict(it, qty=q) if it["op"] == "entry" else it for it in ev.intents], state, lim)
            for i, it in enumerate(ev.intents):
                if it["op"] == "oco":
                    oco[i] = got[i]
                    if got[i] is None:
                        x, y = (index[k] for k in it["ids"])
                        pair[x], pair[y] = y, x
            for i in entries:
                why = LAST_TRADE if (unread and got[i] == door.ONE_AT_A_TIME) else got[i]
                if why is None and q > limits.max_qty:
                    why = f"Size is capped at {limits.max_qty} here."
                if why is None and self._past(ev.intents[i], last):
                    why = PRICE_PAST
                per[i][a] = why
        return per, oco, pair

    @staticmethod
    def _leg(it: dict, last: float | None, tick: float | None):
        """One entry intent as the engine places it. A target given only as an RR goes out as a provisional price
        (entry +/- rr x |entry - stop|) and is re-priced at the fill (engine._lab_move)."""
        from . import engine as engine_mod   # (here: importing this module must load nothing of the tester)
        side = "Buy" if it["side"] == "long" else "Sell"
        sign = 1 if side == "Buy" else -1
        stop = it["kind"] == "stop"
        tp, rr, ref = it.get("tp"), it.get("tp_rr"), it.get("ref")
        base = it["price"] if stop else (ref if ref is not None else last)
        if tp is None and rr is not None and base is not None:
            tp = base + sign * rr * abs(base - it["sl"])
            if tick:
                tp = round(round(tp / tick) * tick, 6)
        return engine_mod.LabLeg(iid=it["id"], side=side, entry="Stop" if stop else "Market",
                                 entry_price=float(it["price"]) if stop else None, sl_px=float(it["sl"]),
                                 tp_px=None if tp is None else float(tp), tp_rr=None if rr is None else float(rr),
                                 ref_px=None if ref is None else float(ref), move=bool(it["move"]))

    def _refused(self, name: str, seq, ids: list, text: str, account: str | None = None,
                 detail: str | None = None) -> None:
        """One refusal, for the journal and the Desk page: {"t", "text", "account"} and, when the engine's answer for
        that account carried the venue's own words, "detail" (plain text, 200 characters at most: the page shows it
        as "The broker refused it: <detail>")."""
        more = {"detail": detail} if detail else {}
        if self.is_lab(name):
            self._rec(name)["refused"].append({"t": self.engine.now_et().strftime("%H:%M:%S"), "text": text,
                                               "account": account, **more})
        else:                                # not a Lab strategy on this Desk: said once a minute per name, at most
            now, last = self._mono(), self._ghost_said.get(name)
            if last is not None and now - last < GHOST_SAY_S:
                return
            if len(self._ghost_said) >= 200:
                self._ghost_said.clear()
            self._ghost_said[name] = now
        self._journal("lab_refused", strategy=name, seq=seq, ids=ids, text=text, account=account, **more)

    # ------------------------------------------------------------ one event
    async def event(self, body) -> dict:
        """One event of one strategy from the runner -> {"ok": True, "seq", "results": [one row per intent, in
        order], "brain": {...}}. ValueError: the body does not read (400). Refused: the Lab side is off (409); too
        many entry requests a second and nothing else in the event to apply (429).
        A row: {"op", ...the intent's id / ids..., "refused": sentence | None} and, for an entry, "status": "working"
        (at least one account took it) | "cancelled" (none did), "accounts": {account: {"ok", "round", "reason"[,
        "detail"]}}; for a cancel / flatten / stop, "accounts": the engine's own answer per account.
        Shielded: a runner that goes away mid-request never leaves an event half applied."""
        if not self.on:
            raise Refused(SWITCHED_OFF)
        ev = parse_event(body)
        limited = False
        if ev.entries:                       # EVERY event that carries an entry is counted, also one that is refused
            mine = self.is_lab(ev.strategy)  # at checks 1-2 (a runner gone wrong must not fill the journal)
            limited = self._too_fast(ev.strategy if mine else None)
            if limited and not ev.exits:     # nothing to apply: 429, and not a line in the journal
                if mine:
                    self._rec(ev.strategy)["refused"].append({"t": self.engine.now_et().strftime("%H:%M:%S"),
                                                              "text": TOO_MANY, "account": None})
                raise Refused(TOO_MANY, 429)
        task = asyncio.ensure_future(self._event_locked(ev, limited))
        task.add_done_callback(lambda t: t.cancelled() or t.exception())     # a result nobody waits for any more
        return await asyncio.shield(task)

    async def _event_locked(self, ev, limited: bool) -> dict:
        if ev.strategy not in self.cfg.strategies:           # nothing of it is on this desk: no lock to grow
            return await self._event(ev, limited)
        async with self._lock(ev.strategy):
            return await self._event(ev, limited)

    async def _event(self, ev, limited: bool) -> dict:
        name = ev.strategy
        known = self.is_lab(name)
        d = self._rec(name) if known else None
        orders = [it for it in ev.intents if it["op"] in intents.ORDER_OPS or it["op"] == "stop"]
        digest = json.dumps(orders, sort_keys=True)
        why, same, booked = None, False, []
        per, oco, pair = ({}, {}, {})
        try:
            # this event counts its `seq` with the promotion the desk knows, today
            same = bool(known and ev.date == d["date"] and list(ev.mark) == labcfg.mark_of(self.cfg, name))
            why = self._stale(ev)                            # 1, 2: refuses the entries only
            if same:
                if d["mark"] != list(ev.mark):               # the day's first event, or a new promotion: its own count
                    d["mark"], d["seq_max"] = list(ev.mark), -1
                    d["answers"].clear()
                    d["digest"].clear()
                # 4: THIS event was answered already (its seq AND its order intents): the same answer, nothing
                # applied. The same seq with other intents is another event (a runner that lost its place): it is
                # never answered from the store -- its exits are applied below, its entries are out of date
                if ev.seq in d["answers"] and d["digest"].get(ev.seq) == digest:
                    return {**d["answers"][ev.seq], "brain": self._brain_now(name)}
                if why is None and ev.entries and ev.seq <= d["seq_max"]:
                    why = OUT_OF_DATE                        # a seq the desk has seen: its orders are old
            if why is None and limited:
                why = TOO_MANY                               # 3 (the event also carries exits: they are applied)
        except Exception as e:  # noqa: BLE001 -- fail closed for the entries; the exits below are still applied
            self._journal("lab_event_error", strategy=name, seq=ev.seq, error=f"{type(e).__name__}: {e}"[:200])
            why = door.CANNOT_CHECK
        if known:                                            # 5: write-ahead (nothing for a name that is not a Lab
            try:                                             # strategy on this Desk: it has no day to rebuild)
                self.engine.journal("lab_event", strategy=name, seq=ev.seq, date=ev.date, mark=list(ev.mark),
                                    counted=same, t_ns=ev.t_ns,
                                    state={"last_price": ev.last_price, "last_ms": ev.last_ms,
                                           "prices_late": ev.prices_late}, intents=orders)
            except Exception:  # noqa: BLE001 -- an entry that cannot be written down is not sent
                why = why or NOT_WRITTEN
        if same:
            d["seq_max"] = max(d["seq_max"], ev.seq)
        try:
            if why is None and ev.entries:
                why = self._not_now(name)                    # 6
            booked = [dict(r) for r in assignments(self.cfg, name)] if known else []
            if why is None and ev.entries and not booked:
                why = OUT_OF_DATE                            # no account is booked: the runner's view of the book is old
            if why is None and ev.entries:
                per, oco, pair = self._verdicts(name, ev, booked)        # 7, 8
        except Exception as e:  # noqa: BLE001 -- fail closed: what cannot be checked is not sent
            self._journal("lab_event_error", strategy=name, seq=ev.seq, error=f"{type(e).__name__}: {e}"[:200])
            why = door.CANNOT_CHECK
        out: list = [None] * len(ev.intents)
        go: bool | None = None                               # the 9:30 hold: asked once, at the event's first entry
        for i, it in enumerate(ev.intents):
            op = it["op"]
            if out[i] is not None:                           # the second leg of a pair: answered with the first
                continue
            try:
                if op == "cancel":
                    out[i] = {"op": op, "id": it["id"], "refused": None,
                              "accounts": await self.engine.lab_cancel(name, it["id"], why="cancel")}
                elif op == "flatten":
                    reason = (it["reason"].strip() or "flat")[:40]
                    out[i] = {"op": op, "refused": None, "accounts": await self.engine.lab_flatten(name, reason=reason)}
                elif op == "stop":
                    out[i] = {"op": op, "refused": None,
                              "accounts": await self._stop(name, it["why"], it["flatten"], cause="runner")}
                elif op == "oco":
                    out[i] = {"op": op, "ids": list(it["ids"]), "refused": oco.get(i)}
                elif op == "entry":
                    unit = [i] + ([pair[i]] if i in pair else [])
                    ids = [ev.intents[j]["id"] for j in unit]
                    no, accounts = why, {}
                    if no is None:
                        accounts, sizes = self._takers(unit, per, booked)
                        if sizes:
                            waited = False
                            if go is None:
                                go, waited = await self._hold()          # 9
                            # the wait yielded: everything the desk itself decides is asked again
                            no = (None if go else FIRE_FIRST) or self._stale(ev) or self._not_now(name)
                            if no is None and waited:
                                # ... and after a wait that really waited, so are the book (who is booked, at what
                                # size), the door and the size cap, on the state as it is NOW. (The price is still
                                # the event's own: the desk has no fresher one on this path.)
                                booked = [dict(r) for r in assignments(self.cfg, name)]
                                if not booked:
                                    no = OUT_OF_DATE
                                else:
                                    per, oco, _ = self._verdicts(name, ev, booked)
                                    accounts, sizes = self._takers(unit, per, booked)
                        if sizes and no is None:
                            rows = await self._enter(name, ev, d, unit, ids, sizes, accounts)
                        else:
                            rows = self._no_entry(name, ev, d, ids, no, accounts)
                    else:
                        rows = self._no_entry(name, ev, d, ids, no, accounts)
                    for j, row in zip(unit, rows):
                        out[j] = row
                else:                                        # a drawing or a note: nothing of the desk's
                    out[i] = {"op": op, "refused": None}
            except Exception as e:  # noqa: BLE001 -- this intent failed; the others (an exit above all) still go
                err = f"{type(e).__name__}: {e}"[:200]
                self._journal("lab_event_error", strategy=name, seq=ev.seq, op=op, error=err)
                out[i] = {"op": op, **({"id": it["id"]} if "id" in it else {}), "error": err,
                          "refused": door.CANNOT_CHECK if op == "entry" else None,
                          **({"status": "cancelled", "accounts": {}} if op == "entry" else {})}
        answer = {"ok": True, "seq": ev.seq, "results": out}
        if same:
            self._keep(d, ev.seq, answer, digest)
        if known:                                            # 11
            self._journal("lab_event_done", strategy=name, seq=ev.seq, mark=list(ev.mark), results=out,
                          entries=d["entries"], untaken=d["untaken"], dead=list(d["dead"]))
        self._publish_safe()
        return {**answer, "brain": self._brain_now(name)}

    @staticmethod
    def _takers(unit: list, per: dict, booked: list) -> tuple:
        """({account: the sentence that refuses this entry there | None}, {account: size} of the ones that may take
        it). A lone leg of a pair never goes out: an account takes both legs or neither, and says the first refused
        leg's sentence."""
        accounts = {r["account"]: next((per[j][r["account"]] for j in unit if per[j][r["account"]]), None) for r in booked}
        return accounts, {r["account"]: int(r["qty"]) for r in booked if accounts[r["account"]] is None}

    def _no_entry(self, name: str, ev, d, ids: list, why: str | None, accounts: dict) -> list:
        """An entry (or a pair) the desk itself refused: it never reached the engine. `why`: one sentence for every
        account, or None when each booked account has its own (`accounts`)."""
        said = {a: (why or s) for a, s in accounts.items()} if accounts else {}
        text = why or next(iter(said.values()), door.CANNOT_CHECK)
        if why is not None or len(set(said.values())) <= 1:
            self._refused(name, ev.seq, ids, text)
        else:
            for a, s in said.items():
                self._refused(name, ev.seq, ids, s, a)
        if d is not None:
            self._dead(d, ids)
        answers = {a: {"ok": False, "round": None, "reason": s} for a, s in said.items()}
        return [{"op": "entry", "id": i, "status": "cancelled", "refused": text, "accounts": answers} for i in ids]

    async def _enter(self, name: str, ev, d: dict, unit: list, ids: list, sizes: dict, accounts: dict) -> list:
        """10: an entry (or a linked pair) on the accounts that may take it. The engine's own answer per account is
        passed back as that account's sentence. It counts as one of today's trades when it reached at least one
        account's broker call (the engine numbered a round for it); two that no account took stop the strategy."""
        limits = labcfg.limits_of(self.cfg, name)
        rec = labcfg.record_of(self.cfg, name) or {}
        last, tick = self._last_price(ev), (tick_size(rec["root"]) if rec.get("root") else None)
        legs = [self._leg(ev.intents[j], last, tick) for j in unit]
        unknown = False
        try:
            got = await self.engine.lab_enter(name, legs, sizes, max_rounds=limits.max_trades_day, source="lab")
            per = got.get("accounts") or {}
            whole = got.get("reason")                        # the engine refused the whole call: no account was asked
        except Exception as e:  # noqa: BLE001 -- the outcome is unknown: counted, and no account is said to hold it
            self._journal("lab_event_error", strategy=name, seq=ev.seq, op="entry", error=f"{type(e).__name__}: {e}"[:200])
            per, whole, unknown = {a: {"ok": False, "round": None, "reason": door.CANNOT_CHECK} for a in sizes}, None, True
        answers = {a: {"ok": False, "round": None, "reason": s} for a, s in accounts.items() if s is not None}
        words = {a: str(r["detail"])[:200] for a, r in per.items() if isinstance(r, dict) and r.get("detail")}
        for a, r in per.items():
            r = r if isinstance(r, dict) else {}
            answers[a] = {"ok": r.get("ok") is True, "round": r.get("round"),
                          "reason": r.get("reason") or (None if r.get("ok") is True else door.CANNOT_CHECK),
                          **({"detail": BROKER_REFUSED + str(r["detail"])} if r.get("detail") else {}),
                          **({"warning": r["warning"]} if r.get("warning") else {})}
        took = any(r["ok"] for r in answers.values())
        if unknown or any(r["round"] is not None for r in answers.values()):
            d["entries"] += 1                                # a pair is one trade
        said = {a: r["reason"] for a, r in answers.items() if not r["ok"]}
        text = None
        if not took:
            text = whole or next(iter(said.values()), door.CANNOT_CHECK)
            self._dead(d, ids)
            if whole is None:
                d["untaken"] += 1                            # it was offered to its accounts and none took it
        if not took and whole is not None:
            self._refused(name, ev.seq, ids, text)           # the engine refused the whole call: no account was asked
        else:
            for a, why in said.items():                      # every account that did not take it, by name, with its
                self._refused(name, ev.seq, ids, why, a, words.get(a))     # own sentence and the venue's words
        rows = [{"op": "entry", "id": i, "status": "working" if took else "cancelled", "refused": text,
                 "accounts": answers} for i in ids]
        if not took and d["untaken"] >= 2 and d["stopped"] is None:
            await self._stop(name, STOPPED_TODAY, False, cause="untaken")
        return rows

    # ------------------------------------------------------------ stop
    async def stop(self, name: str, why: str, flatten: bool = False) -> dict:
        """Stop a Lab strategy for today: its unfilled entries are cancelled; with `flatten` (it crashed or hung) its
        own position is closed at once by the engine's capped flatten, else the position keeps its broker stop and
        the desk's flat time. From the runner (a `stop` intent), from the Desk's switch (why "off"), and by the desk
        itself. Entries are refused "Stopped for today." from here on; it is journaled (`lab_stopped`) and survives a
        desk restart. Never raises. -> the engine's answer per account."""
        if not self.on:
            return {}
        try:
            if name in self.cfg.strategies:
                async with self._lock(name):                 # after an event of this strategy that is being applied
                    return await self._stop(name, why, flatten, cause="desk")
            return await self._stop(name, why, flatten, cause="desk")
        except Exception as e:  # noqa: BLE001
            self._journal("lab_event_error", strategy=name, op="stop", error=f"{type(e).__name__}: {e}"[:200])
            return {}

    async def _stop(self, name: str, why, flatten: bool, *, cause: str) -> dict:
        why = (str(why or "").strip() or STOPPED_TODAY)[:200]
        known = self.is_lab(name)
        first = False
        if known:
            d = self._rec(name)
            first = d["stopped"] is None
            if first:
                d["stopped"] = why                           # before the await: no entry of this strategy passes it
            # ... and written down before the engine is asked: a desk that goes down in the middle still knows
            # (what the engine then did is in its own lines: lab_cancelled / lab_flatten)
            self._journal("lab_stopped", strategy=name, why=why, flatten=bool(flatten), cause=cause, first=first)
        try:
            if flatten:
                res = await self.engine.lab_flatten(name, reason="stopped")
            else:
                res = await self.engine.lab_cancel(name, None, why="stopped")
        except Exception as e:  # noqa: BLE001
            res = {"error": f"{type(e).__name__}: {e}"[:200]}
        self._publish_safe()
        return res

    # ------------------------------------------------------------ a carried block, cleared by hand
    async def clear_block(self, name: str, account: str) -> dict:
        """The owner's "this account is fine" for a block carried from an earlier day (engine.lab_clear_block: only
        with the position at exactly 0 and no known order of that trade still working; it sends nothing). It needs
        the Lab side on, and NOT the store: it books nothing. Refused with the engine's sentence."""
        if not self.on:
            raise Refused(SWITCHED_OFF)
        if not self._lab_kind(name):
            raise Refused(NOT_ON_DESK, 404)
        got = await self.engine.lab_clear_block(name, account)
        if not got.get("ok"):
            raise Refused(str(got.get("reason") or door.CANNOT_CHECK), 404 if got.get("reason") == NOT_ON_DESK else 409)
        self._publish_safe()
        return {"ok": True, "cleared": got.get("cleared") or []}

    # ------------------------------------------------------------ the heartbeat (design C4)
    def heartbeat(self, body) -> dict:
        """The runner's beat, every 5 s: {"pid", "strategies": {desk id: {"state", "why", "mode"}}} ->
        {"ok": True, "armed", "strategies": {desk id: {"enabled", "killed", "stopped"}}} for the ones on this Desk.
        ValueError: the body does not read."""
        if not self.on:
            raise Refused(SWITCHED_OFF)
        named = body.get("strategies") if isinstance(body, dict) else None
        if not isinstance(body, dict) or isinstance(body.get("pid"), bool) or not isinstance(body.get("pid"), int) \
                or not isinstance(named, dict) or len(named) > 200:
            raise ValueError(NOT_READ)
        now, out = self._mono(), {}
        for name, said in named.items():
            if not isinstance(name, str) or not self.is_lab(name):
                continue
            said = said if isinstance(said, dict) else {}
            live = self._alive(name)
            live["beat"] = now
            live["info"] = {"state": said.get("state") if isinstance(said.get("state"), str) else None,
                            "why": said["why"][:200] if isinstance(said.get("why"), str) else None,
                            "mode": said.get("mode") if said.get("mode") in ("shadow", "desk") else None}
            live["fired"].clear()                # a new silence is judged afresh
            if live["down"]:
                live["down"] = False
                self._journal("lab_runner_back", strategy=name)
            out[name] = {"enabled": bool(self.cfg.strategies[name].enabled), "killed": self.engine.killed_today(name),
                         "stopped": self._rec(name)["stopped"]}
        return {"ok": True, "armed": bool(self.cfg.armed), "strategies": out}

    def _has_open_round(self, name: str) -> bool:
        """A round of today the engine still acts on (placing, placed or live, at its account's plain key)."""
        return any(st.status in OPEN and self.engine.states.get(f"{name}@{st.account}") is st
                   for st in self.engine.day_states(name))

    async def _runner_rule(self) -> None:
        """No beat naming a strategy for RUNNER_ALIVE_S (monotonic, counted from the desk's start) while it has an
        open round: its unfilled entries are cancelled (`lab_runner_down`), ONCE PER ROUND -- a round opened after the
        rule fired (an event is not a beat) is guarded too, and a position that stays open is spoken of once, not on
        every pass. Never a flatten: an open position keeps its broker stop and the engine's flat time."""
        now = self._mono()
        for name in list(labcfg.lab_ids(self.cfg)):
            live = self._alive(name)
            last = live["beat"] if live["beat"] is not None else self._t0
            if now - last < RUNNER_ALIVE_S or not self._has_open_round(name):
                continue
            rounds = {(r.get("account"), r.get("round"), r.get("date")) for r in self._rows(name)
                      if r.get("status") in OPEN and not r.get("carried")}
            if not rounds - live["fired"]:
                continue                                     # every open round was dealt with: nothing more to say
            lock = self._lock(name)
            if lock.locked():                                # an event of it is being applied: the next pass
                continue
            live["fired"] |= rounds                          # before the await: once for each of them
            live["down"] = True
            async with lock:
                try:
                    res = await self.engine.lab_cancel(name, None, why="runner_down")
                except Exception as e:  # noqa: BLE001
                    res = {"error": f"{type(e).__name__}: {e}"[:200]}
            self._journal("lab_runner_down", strategy=name, silent_s=round(now - last, 1), results=res)

    async def _both_filled_rule(self) -> None:
        """Both legs of a pair filled on an account (the engine's emergency: that round is `error` / both_filled and a
        person must look): the desk stops the strategy for today, ONCE per such account -- the other accounts'
        unfilled entries are cancelled and the runner is told (`stopped` on the stream). Never waits for an event
        that is being applied: the next pass."""
        for name in list(labcfg.lab_ids(self.cfg)):
            hit = [st.account for st in self.engine.day_states(name)
                   if st.status == "error" and st.exit_reason == "both_filled"
                   and self.engine.states.get(f"{name}@{st.account}") is st]
            if not hit:
                continue
            d = self._rec(name)
            new = [a for a in hit if a not in d["both"]]
            lock = self._lock(name)
            if not new or lock.locked():
                continue
            d["both"] += new                                 # before the await: once
            async with lock:
                await self._stop(name, BOTH_FILLED, False, cause="both_filled")

    # ------------------------------------------------------------ the stream back (design C5, D7)
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUB_QUEUE_MAX)
        self._subs.add(q)
        return q

    def unsubscribe(self, q) -> None:
        self._subs.discard(q)

    def _publish(self, event: str, data: dict) -> None:
        """Never waits for a reader: one that is SUB_QUEUE_MAX behind is dropped with an end marker and reconnects
        (its first event is then a whole state)."""
        for q in list(self._subs):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                self._subs.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait((None, None))

    def _snap(self, name: str) -> dict:
        """One strategy, whole (level triggered: no edge is ever needed to read it)."""
        rows = self._rows(name)
        d = self._rec(name)
        keep = ("account", "round", "status", "date", "carried", "iid", "qty", "entry_side", "entry_qty", "entry_fill",
                "exit_qty", "exit_fill", "exit_reason", "sl", "tp", "pnl", "clean", "entry_ms", "exit_ms", "why")
        return {"strategy": name, "mark": labcfg.mark_of(self.cfg, name), "date": d["date"],
                "enabled": bool(self.cfg.strategies[name].enabled), "armed": bool(self.cfg.armed),
                "killed": self.engine.killed_today(name), "stopped": d["stopped"],
                "brain": self._brain(name, rows), "rounds": [{k: r.get(k) for k in keep} for r in rows],
                "answered": sorted(d["answers"])}

    def snapshot(self) -> dict:
        """The `state` snapshot: every Lab strategy on this Desk, whole."""
        out = {}
        for name in labcfg.lab_ids(self.cfg) if self.on else ():
            if name in self.cfg.strategies:
                out[name] = self._snap(name)
        return {"date": self.engine._today(), "armed": bool(self.cfg.armed), "strategies": out}

    def publish_changed(self) -> bool:
        """Send every reader the snapshots that changed since the last send. Nothing when nobody listens, and nothing
        while a strategy that is not from the Lab is placing or in the seconds around a timer strategy's fire (no
        snapshot is built then: the next pass after it carries the level). True when it published."""
        if not self.on or not self._subs or self._fire_first():
            return False
        ids = [n for n in labcfg.lab_ids(self.cfg) if n in self.cfg.strategies]
        if any(n not in ids for n in self._last):            # one left the Desk: a whole state says so
            snap = self.snapshot()
            self._last = dict(snap["strategies"])
            self._publish("state", snap)
            return True
        sent = False
        for name in ids:
            snap = self._snap(name)
            if snap != self._last.get(name):
                self._last[name] = snap
                self._publish("strategy", snap)
                sent = True
        return sent

    def _publish_safe(self) -> None:
        """Right after an intake action. A snapshot that cannot be built never fails the action."""
        try:
            self.publish_changed()
        except Exception as e:  # noqa: BLE001
            self._say_tick(e)

    def _say_tick(self, e: Exception) -> None:
        msg, now = f"{type(e).__name__}: {e}"[:200], time.monotonic()
        if self._said_tick is None or self._said_tick[0] != msg or now - self._said_tick[1] >= 60.0:
            self._said_tick = (msg, now)
            self._journal("lab_intake_error", error=msg)

    async def _intake_tick(self) -> None:
        """run()'s publish step: the heartbeat rule, the both-legs-filled stop, then the snapshots that changed.
        Never raises."""
        try:
            await self._runner_rule()
            await self._both_filled_rule()
            self.publish_changed()
        except Exception as e:  # noqa: BLE001 -- the next pass tries again
            self._say_tick(e)

    def _lab_calls(self) -> None:
        """One Lab call per strategy (engine.lab_open): the engine rolls its Lab day, and carries an unresolved round
        as a block, only at a Lab call -- so one is made at the start, before the first fill can arrive, and on every
        refresh pass (also while the refresh's disk part is skipped). Memory and the engine's own files only."""
        ask = getattr(self.engine, "lab_open", None)
        for name in list(labcfg.lab_ids(self.cfg)) if ask is not None else ():
            with contextlib.suppress(Exception):
                ask(name)
        for box in (self._hits, self._live, self._locks):    # a strategy that left the Desk leaves these too
            for name in [n for n in box if n is not None and n not in self.cfg.strategies]:
                del box[name]

    # ------------------------------------------------------------ the start
    def start(self) -> None:
        """The desk's start (the server's lifespan), before anything is served: one journal line, `lab_side`, says the
        Lab side is on; a Lab round the day file holds for a strategy that is not on this Desk is said (once each);
        with the Lab side on, today's intake counters come back from the journal and the first Lab call is made.
        Never raises: a Lab problem never stops the desk.
        With the Lab side OFF nothing is journaled (a desk without the flag is, line for line, the desk it was before
        Step B: tests/test_server_lab.py pins that its status holds no Lab word at all) -- it says so on stderr only,
        unless it finds such a round."""
        if self.on:
            self._journal("lab_side", on=True)
        else:
            print("homebase desk: the Lab side is off (no lab_desk.on in this checkout's state folder)", file=sys.stderr)
        try:
            for name, account, status in orphans(self.cfg, self.engine):
                if (name, account) not in self._orphans_said:
                    self._orphans_said.add((name, account))
                    self._journal("lab_open_without_cfg", strategy=name, account=account, status=status, lab_side=self.on)
        except Exception as e:  # noqa: BLE001
            log.warning("the Lab rounds of the day file could not be checked at the start: %s", e)
        if not self.on:
            return
        try:
            self._restore()
        except Exception as e:  # noqa: BLE001 -- unknown counters: fail closed below
            log.warning("the Lab intake could not be rebuilt from the journal: %s", e)
            self._journal("lab_restore_error", error=f"{type(e).__name__}: {e}"[:200])
        self._lab_calls()

    def _restore(self) -> None:
        """Today's intake records, rebuilt from the journal's own lines (as the engine rebuilds its kills): every
        answered `seq` with its answer, trades a day, the entries no account took, stopped for today, the refusals.
        An event that was written ahead and never answered (the desk went down in the middle) is counted as a trade
        when it carried an entry, and its `seq` is never taken again: fail closed."""
        p = self.engine.journal_path
        if not p.exists():
            return
        today = self.engine._today()
        open_events: dict = {}                               # (strategy, seq) -> it carried an entry
        digests: dict = {}                                   # (strategy, seq) -> its COUNTED event's order intents
        for line in p.read_text(errors="replace").splitlines():
            if '"lab_' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or not str(r.get("et", "")).startswith(today):
                continue
            ev, name, seq = r.get("event"), r.get("strategy"), r.get("seq")
            if not isinstance(name, str) or labcfg.store_name(name) is None:
                continue
            d = self._rec(name)
            whole = isinstance(seq, int) and not isinstance(seq, bool)
            if ev == "lab_event" and whole:
                held = r.get("intents") if isinstance(r.get("intents"), list) else []
                open_events[(name, seq)] = any(isinstance(i, dict) and i.get("op") == "entry" for i in held)
                # the mark, the seq count and the answered set come ONLY from lines the live desk counted (an event
                # made for another promotion or another day is written down too -- its exits were applied -- and
                # must never reset them)
                if r.get("counted") is True and isinstance(r.get("mark"), list):
                    if d["mark"] != r["mark"]:
                        d["mark"], d["seq_max"] = list(r["mark"]), -1
                        d["answers"].clear()
                        d["digest"].clear()
                    d["seq_max"] = max(d["seq_max"], seq)
                    digests[(name, seq)] = json.dumps(held, sort_keys=True)
                else:
                    digests.pop((name, seq), None)
            elif ev == "lab_event_done" and whole:
                open_events.pop((name, seq), None)
                digest = digests.pop((name, seq), None)
                if digest is not None and isinstance(r.get("mark"), list) and r["mark"] == d["mark"]:
                    self._keep(d, seq, {"ok": True, "seq": seq, "results": r.get("results") or []}, digest)
                for k in ("entries", "untaken"):
                    if isinstance(r.get(k), int) and not isinstance(r.get(k), bool):
                        d[k] = max(d[k], r[k])
                self._dead(d, [i for i in r.get("dead") or [] if isinstance(i, int)])
            elif ev == "lab_stopped" and d["stopped"] is None:
                d["stopped"] = str(r.get("why") or STOPPED_TODAY)
            elif ev == "lab_refused" and isinstance(r.get("text"), str):
                d["refused"].append({"t": str(r.get("et", ""))[11:19], "text": r["text"], "account": r.get("account"),
                                     **({"detail": r["detail"][:200]} if isinstance(r.get("detail"), str) and r["detail"] else {})})
        for (name, _), carried_entry in open_events.items():
            if carried_entry:
                self._rec(name)["entries"] += 1
        for d in self._days.values():                        # two entries no account took stop the day, whether or
            if d["date"] == today and d["stopped"] is None and d["untaken"] >= 2:     # not the stop's own line was written
                d["stopped"] = STOPPED_TODAY

    # ------------------------------------------------------------ what the status block shows of the intake
    def _intake_view(self, name: str, state: str, why) -> dict:
        """The fields of status_view the intake half owns: trades a day, how the runner hosts it today, the last
        refusals, and the states only the runner or the intake can tell (runner down, stopped, watching, done)."""
        d, live = self._rec(name), self._alive(name)
        info = live["info"] or {}
        fresh = live["beat"] is not None and self._mono() - live["beat"] < RUNNER_ALIVE_S
        if state != "check":
            if live["down"] and state in ("working", "in_position"):
                state, why = "runner_down", None
            elif state in ("waiting", "disarmed") and d["stopped"] is not None:
                state, why = "stopped", d["stopped"]
            elif state == "waiting" and fresh:
                told = {"running": "watching", "done": "done", "not_today": "done", "stopped": "stopped"}.get(info.get("state"))
                if told is not None:
                    state, why = told, (info.get("why") if told == "stopped" else None)
        return {"state": state, "why": why, "trades_today": d["entries"],
                "mode_today": info.get("mode") if fresh else None, "refused": list(d["refused"])}


# ---------------------------------------------------------------------------------------------- the intake half, module level
@dataclass(frozen=True)
class LabEvent:
    """One event of one strategy, as the runner posts it (design C2), parsed."""
    strategy: str
    date: str
    mark: tuple
    seq: int
    t_ns: int | None
    last_price: float | None
    last_ms: int | None
    prices_late: bool
    intents: tuple                           # every intent, in call order

    @property
    def entries(self) -> list:
        return [it for it in self.intents if it["op"] == "entry"]

    @property
    def exits(self) -> list:
        return [it for it in self.intents if it["op"] in EXITS]


def _whole(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def parse_event(body) -> LabEvent:
    """A ValueError carries one sentence (the route answers 400). Every intent passes labrun.intents.well_formed (the
    host's own rule) or is the runner's `stop`; at most MAX_ORDERS of them are orders; an order id is used once."""
    if not isinstance(body, dict):
        raise ValueError(NOT_READ)
    name, date, mark, seq, t_ns = (body.get(k) for k in ("strategy", "date", "mark", "seq", "t_ns"))
    state, held = body.get("state"), body.get("intents")
    if not (isinstance(name, str) and 0 < len(name) <= 80 and isinstance(date, str) and _DATE.fullmatch(date)
            and isinstance(mark, list) and len(mark) == 2 and all(v is None or isinstance(v, str) for v in mark)
            and _whole(seq) and seq >= 0 and (t_ns is None or _whole(t_ns))
            and isinstance(state, dict) and isinstance(held, list)):
        raise ValueError(NOT_READ)
    last, last_ms = state.get("last_price"), state.get("last_ms")
    if last is not None and not door._num(last):
        raise ValueError(NOT_READ)
    if last_ms is not None and not _whole(last_ms):
        raise ValueError(NOT_READ)
    if not all(intents.well_formed(it) or intents.well_formed_stop(it) for it in held):
        raise ValueError("An order in this request does not read.")
    if sum(1 for it in held if it["op"] in intents.ORDER_OPS or it["op"] == "stop") > MAX_ORDERS:
        raise ValueError(TOO_MANY)
    ids = [it["id"] for it in held if it["op"] == "entry"]
    if len(ids) != len(set(ids)):
        raise ValueError("An order in this request does not read.")
    return LabEvent(strategy=name, date=date, mark=tuple(mark), seq=seq, t_ns=t_ns,
                    last_price=None if last is None else float(last), last_ms=last_ms,
                    prices_late=state.get("prices_late") is not False,      # anything but a plain "no" is late
                    intents=tuple(dict(it) for it in held))


def orphans(cfg: AppCfg, engine) -> list:
    """[(strategy, account, status)]: Lab rounds of TODAY that the engine holds open -- placing, placed or live, or a
    placement a restart left unknown -- for a strategy that is not a Lab strategy on this Desk (the Lab side is off,
    or its record is gone). The engine's clock skips a state whose strategy it does not know: nothing cancels such a
    round's entries and nothing closes it at the flat time. Memory only."""
    out, today = [], engine._today()
    for st in list(engine.states.values()):
        name = getattr(st, "strategy", None)
        if not isinstance(name, str) or labcfg.store_name(name) is None or getattr(st, "date", None) != today:
            continue
        s = cfg.strategies.get(name)
        if s is not None and getattr(s, "kind", "") == LAB:
            continue
        if st.status in OPEN or (st.status == "error" and st.note == PLACING_UNKNOWN):
            out.append((name, st.account, st.status))
    return out


def orphan_line(cfg: AppCfg, engine) -> dict | None:
    """The ONE readiness line for the rounds orphans() finds; None when there is none. Never raises."""
    try:
        if orphans(cfg, engine):
            return {"level": "bad", "label": "Lab strategies", "detail": OPEN_WITHOUT_CFG}
    except Exception:  # noqa: BLE001 -- readiness is the whole desk's: a Lab problem adds no line, never breaks it
        pass
    return None
