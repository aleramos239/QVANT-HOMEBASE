"""The desk's side of a promoted Lab strategy (Step B). This file is the CONFIG half (task B1): the desk knows the
strategy, keeps its limits and its book, switches it, removes it and says what it is doing. The INTAKE half (task B3:
the runner's orders, the stream, the heartbeat rule) is added to this class later; until then nothing here, and nothing
that calls it, can send an order.

    attach(cfg)            the desk's start: overlay the promoted strategies on the config, register the sidecar writer
                           as config.save's after-save hook. Never raises: a Lab problem never stops the desk.
    LabDesk.refresh()      every 2 s (run()): the store is read in a thread, the config is changed on the loop. Skipped
                           while the chart views are paused (a bot is placing, the seconds around a fire).
    LabDesk.set_limits     the owner's limits, checked (labcfg.parse_limits); not 09:20-09:35 ET, not with a round open.
    LabDesk.check_book     asked before EVERY strategy's book write: one strategy per market per account when a Lab
                           strategy is one of the two; for a Lab strategy also its limits, its size cap, one broker
                           account once, and no account taken off while it has a round open.
    LabDesk.set_enabled    the ONE switch: the store record's `enabled` (the runner hosts by it).
    LabDesk.remove         off the Desk: sidecar and record go, the history stays. Not with a round open.
    LabDesk.status_view    the `lab` block of /api/status.

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
RUNNER_ALIVE_S = 20                      # the runner is alive while its heartbeat is at most this old
QUIET = (dt.time(9, 20), dt.time(9, 35))   # weekdays ET: the 9:30 window (limits are not changed in it)
OPEN = ("placing", "placed", "live")     # a round the engine still acts on

NOT_ON_DESK = "That strategy is not on the Desk."
SET_LIMITS_FIRST = "Set the limits first."
FLATTEN_FIRST = "Flatten it first."
NOT_NOW = "Not 09:20-09:35 ET. Try again after 09:35."
NOT_SAVED = "Could not save it. Try again."
RECORD_CHANGED = "The Lab record changed. Try again."


class Refused(Exception):
    """A request the desk will not take. str(e) is the sentence the page shows; `status` is the HTTP status."""

    def __init__(self, sentence: str, status: int = 409):
        super().__init__(sentence)
        self.status = status


def attach(cfg: AppCfg, at=None) -> None:
    """The desk's start, right after config.load(): the promoted strategies join the config in memory (never
    config.json), and every later config.save also writes the sidecars that changed. Never raises."""
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
        self._at = at if at is not None else cfg.__dict__.get("_lab_at")
        self._gen = 0                    # bumped by every change the desk itself makes: a store read that began
                                         # before one is thrown away (it may hold what the change replaced)
        self._seen_utc: dt.datetime | None = None    # the runner's heartbeat, as last read
        self._said: tuple | None = None  # (error text, monotonic) of the last lab_refresh_error line

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

    def _save_sidecars(self) -> bool:
        """Write what changed, now. False when a sidecar could not be written (it stays pending)."""
        try:
            labcfg.persist_all(self.cfg, self._at)
        except Exception as e:  # noqa: BLE001 -- the caller undoes its change and says so
            self._journal("lab_save_error", error=str(e)[:200])
        return not labcfg.pending(self.cfg)

    def _journal(self, event: str, **kw) -> None:
        with contextlib.suppress(Exception):
            self.engine.journal(event, **kw)

    # ------------------------------------------------------------ the 2 s refresh
    def _read(self) -> tuple:
        """The disk half, in a thread: every record with its sidecar, and the runner's heartbeat."""
        return labcfg.read_store(self._at), store.get_runner(self._at)

    async def refresh(self) -> dict | None:
        """Bring the config in line with the store. None when it was skipped: the views are paused (before the read,
        or by the time it came back), or the desk changed something while the read ran."""
        if self._paused():
            return None
        gen = self._gen
        snap, beat = await asyncio.to_thread(self._read)
        if gen != self._gen or self._paused():
            return None
        out = labcfg.apply(self.cfg, snap, held=lambda did: bool(self._open(did)))
        try:
            seen = dt.datetime.fromisoformat((beat or {}).get("seen_utc"))
            self._seen_utc = seen if seen.tzinfo is not None else seen.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            self._seen_utc = None
        for did in out["added"]:
            self._journal("lab_added", strategy=did, mark=labcfg.mark_of(self.cfg, did))
        for did in out["removed"]:
            self._journal("lab_removed", strategy=did, cause="record_gone")
        if labcfg.pending(self.cfg):         # a dropped book, a cleaned row, a write that failed earlier
            labcfg.persist_all(self.cfg, self._at)
        return out

    async def run(self, interval_s: float = REFRESH_S) -> None:
        """The background task. An error is journaled (the same one once a minute at most) and never ends it."""
        while True:
            try:
                await self.refresh()
            except Exception as e:  # noqa: BLE001 -- the next round tries again
                msg, now = str(e)[:200], time.monotonic()
                if self._said is None or self._said[0] != msg or now - self._said[1] >= 60.0:
                    self._said = (msg, now)
                    self._journal("lab_refresh_error", error=msg)
            await asyncio.sleep(interval_s)

    # ------------------------------------------------------------ limits
    async def set_limits(self, name: str, body) -> dict:
        """ValueError: a bad field, with its sentence. Refused: not a Lab strategy (404), the 9:30 window, a round
        open, or the sidecar could not be written (500; nothing is kept then)."""
        self._need(name)
        limits = labcfg.parse_limits(body, labcfg.record_of(self.cfg, name))
        if self._in_quiet():
            raise Refused(NOT_NOW)
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        was = labcfg.limits_of(self.cfg, name)
        self._gen += 1
        labcfg.set_limits(self.cfg, name, limits)
        if not self._save_sidecars():
            labcfg.set_limits(self.cfg, name, was)
            raise Refused(NOT_SAVED, 500)
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

    def book_saved(self, name: str) -> bool:
        """After a Lab strategy's book write: True when its sidecar holds it (config.save's hook wrote it, or this
        call does). False: the route puts the old book back and says so."""
        return not self.is_lab(name) or self._save_sidecars()

    # ------------------------------------------------------------ the switch
    async def set_enabled(self, name: str, on: bool) -> bool:
        """Write the store record's `enabled`. Switching ON needs the promotion the desk knows (False: the record was
        promoted again, or is gone -- the page says "The Lab record changed. Try again."). Switching OFF is never
        refused: off is off whatever the record now is."""
        if not self.is_lab(name):
            return False
        on = bool(on)
        sname, mark = labcfg.store_name(name), labcfg.mark_of(self.cfg, name)
        self._gen += 1
        rec = await asyncio.to_thread(store.set_enabled, sname, on, self._at, mark if on else None)
        self._gen += 1
        if rec is None and on:
            return False
        if labcfg.is_lab(self.cfg, name):    # still here after the wait
            labcfg.set_enabled(self.cfg, name, on)
        return True

    # ------------------------------------------------------------ remove
    def _remove_files(self, sname: str) -> None:
        with store.write_lock(self._at):
            store.remove_desk(sname, self._at)
            store.remove(sname, self._at)

    async def remove(self, name: str) -> dict:
        self._need(name)
        if self._open(name):
            raise Refused(FLATTEN_FIRST)
        accounts = [r["account"] for r in assignments(self.cfg, name)]
        self._gen += 1
        self.cfg.book.pop(name, None)        # first: from here on no account is assigned to it
        try:
            await asyncio.to_thread(self._remove_files, labcfg.store_name(name))
        except Exception as e:  # noqa: BLE001 -- it stays on the Desk with no account; the page says so
            self._journal("lab_save_error", strategy=name, error=str(e)[:200])
            raise Refused(NOT_SAVED, 500) from None
        finally:
            self._gen += 1
        labcfg.forget(self.cfg, name)
        self._journal("lab_removed", strategy=name, cause="removed", unbooked=accounts)
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
        except Exception as e:  # noqa: BLE001
            return {"name": sname, "mark": None, "limits": None, "state": "check", "why": f"The Desk cannot read it: {str(e)[:80]}",
                    "trades_today": 0, "mode_today": None, "runner": {"alive": False, "age_s": None}, "rounds": [], "refused": []}
