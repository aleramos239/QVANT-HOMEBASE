"""A promoted Lab strategy as a desk strategy (Step B, 2026-10-10): its id, its limits, the overlay, the sidecar.

The desk learns about promoted strategies (homebase/labrun/store.py) by OVERLAYING them on its config in memory, as
strategies of kind "lab" with the id `lab_<name>`. They are never written to config.json: config.load() drops a strategy
it does not ship, with its book rows, and other processes call it. What the desk itself decides about one -- its limits
and which accounts trade it (the book) -- is kept in a sidecar file beside the record, <store>/<name>.desk.json, written
by the desk process only:

    {"mark": [sha256, promoted_utc], "limits": {...} | None, "book": [{"account", "qty"}], "written_utc"}

Who is the truth:
  * the record (code, market, window, size, costs, `enabled`): the store. overlay() re-reads it and follows it;
  * the limits and the book: the desk's memory, once the strategy is known here. The sidecar is read ONCE, when the
    strategy first appears (a desk start, a new promotion); after that overlay() never takes them from disk again, so a
    store read that began before a booking can never undo it;
  * the mark names one promotion. A sidecar of another promotion, or a strategy promoted again while the desk runs,
    loses its book and keeps its limits (when they still fit the new record's window).

The load path holds the routes' rules, at the first appearance and on every apply():
  * no limits (none set, or they do not parse) -> NO book; a row above "most contracts" is dropped. Every book the desk
    drops on its own is noted (`lab_unbooked`: strategy, accounts, why);
  * the rules judge only the rows of accounts THIS desk has. A row of an account that is not in its pool is kept, in
    cfg.book and in the sidecar, exactly as it is: it is simply not active (config.assignments() filters on the pool).
    A desk never un-books on disk an account merely because it does not have it; removing an account from the desk
    (server.py) is the one path that strips its rows;
  * limits that were on disk (or in memory) but do not parse against the record FREEZE the sidecar: it is left on disk
    exactly as it is -- never `limits: null` over what he typed -- until he saves limits again;
  * one record that cannot be made a strategy is skipped (`lab_unreadable`, once per promotion) and the others load. One
    already on the desk is kept as it last read, switched off, until its record reads again.

One desk owns a store: take_store() (an exclusive lock on <store>/desk.lock, for the life of the process). Only the
owner writes sidecars; a config that never took the store, or could not, reads only -- and then its limits and book
FOLLOW the owner's sidecar (apply(reload=True)), so that a reader which later gets the lock takes over with what is on
disk, not with what it read at its start. A lock that could not even be tried (an OSError) is "unknown", not "another
desk": both are tried again.

A record is GONE only when its file is absent from the store. A file that is there and does not read (permissions, too
many open files, garbage) is a record the desk cannot read: the strategy stays, switched off, and its sidecar is never
touched.

The pieces are split so the desk can keep disk work off its event loop: read_store() is the only reader (run it in a
thread), apply() only touches memory (run it on the loop: every other reader of cfg.strategies iterates it without
awaiting), pending() only compares memory, persist_all() writes the sidecars that changed and NEVER waits for the store
unless told to (it is config.save's hook: a store held by another process must not hold up a save, or a Kill).
What apply() has to say goes to a short queue on the config (take_notes): the desk journals it.

Nothing here runs strategy code, and nothing here is imported from homebase.backtest (tests/test_labcfg.py pins it).
Stdlib + config + the store.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import math
import re
from dataclasses import asdict, dataclass

from .config import AppCfg, StrategyCfg
from .labrun import store

LAB = "lab"                              # StrategyCfg.kind
PREFIX = "lab_"                          # desk id = PREFIX + the store name
FLAT_LATEST = "15:55"                    # version 1: flat no later than this, for every market
RISK_MOST = 1e9                          # a sanity bound: "at risk per trade" above it is not a dollar amount
NOTES_KEPT = 200                         # what apply() has to say, until the desk journals it
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

SAY_TRADES = "Trades a day: a whole number from 1 to 20."
SAY_QTY = "Contracts: a whole number from 1 to 10."
SAY_RISK = "At risk per trade: a dollar amount above 0."
SAY_LAST = "No new trade after: a time like 11:00, before the flat time."
SAY_FLAT = "Flat by: a time like 15:55, no later than 15:55."


def desk_id(name: str) -> str:
    return PREFIX + name


def store_name(desk_id) -> str | None:
    """The store name of a desk id; None for an id that is not a Lab strategy's."""
    if isinstance(desk_id, str) and desk_id.startswith(PREFIX) and len(desk_id) > len(PREFIX):
        return desk_id[len(PREFIX):]
    return None


# ------------------------------------------------------------------ limits
@dataclass(frozen=True)
class LabLimits:
    max_trades_day: int      # 1..20
    max_qty: int             # 1..10, contracts per account
    max_risk_usd: float      # > 0, per trade per account
    last_entry_et: str       # "HH:MM", >= the record's session_window[0]
    flat_et: str             # "HH:MM", > last_entry_et, <= "15:55"


def _whole(v, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _number(v, lo: float, hi: float) -> bool:
    """A real, finite number in [lo, hi]. An int too large for a float is not one (math.isfinite raises on it)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v) and lo <= v <= hi
    except OverflowError:
        return False


def _hhmm(v) -> bool:
    return isinstance(v, str) and HHMM.fullmatch(v) is not None


def window(rec: dict) -> tuple[str, str]:
    """The record's session window as two "HH:MM" strings; the Strategy's default one when it does not read."""
    w = rec.get("session_window")
    if isinstance(w, (list, tuple)) and len(w) == 2 and _hhmm(w[0]) and _hhmm(w[1]):
        return w[0], w[1]
    return store.DEFAULT_WINDOW[0], store.DEFAULT_WINDOW[1]


def parse_limits(body, rec: dict) -> LabLimits:
    """The limits the owner typed, checked. A ValueError carries the one sentence the dialog shows."""
    if not isinstance(body, dict):
        raise ValueError(SAY_TRADES)
    trades, qty, risk = body.get("max_trades_day"), body.get("max_qty"), body.get("max_risk_usd")
    last, flat = body.get("last_entry_et"), body.get("flat_et")
    if not _whole(trades, 1, 20):
        raise ValueError(SAY_TRADES)
    if not _whole(qty, 1, 10):
        raise ValueError(SAY_QTY)
    if not _number(risk, 0, RISK_MOST) or not risk > 0:
        raise ValueError(SAY_RISK)
    if not _hhmm(last):
        raise ValueError(SAY_LAST)
    if not _hhmm(flat) or flat > FLAT_LATEST:
        raise ValueError(SAY_FLAT)
    if not window(rec)[0] <= last < flat:                # "HH:MM" strings compare as times
        raise ValueError(SAY_LAST)
    return LabLimits(trades, qty, float(risk), last, flat)


def _limits_from(saved, rec: dict) -> LabLimits | None:
    """Limits as a sidecar holds them; None when there are none or they no longer read (the owner sets them again)."""
    try:
        return parse_limits(saved, rec) if saved is not None else None
    except ValueError:
        return None


# ------------------------------------------------------------------ record -> StrategyCfg
def usable(rec) -> bool:
    """A record the desk can make a strategy of: it names itself and its market."""
    return (isinstance(rec, dict) and isinstance(rec.get("name"), str) and bool(rec.get("name"))
            and isinstance(rec.get("root"), str) and bool(rec.get("root")))


def strategy_cfg(rec: dict, limits: LabLimits | None) -> StrategyCfg:
    """The desk's view of a promoted strategy. No geometry (the strategy sends its own prices); the times are the
    limits', or -- with none set, when no account can be assigned -- the record's window cut at 15:55. self_fire is True
    so inactive.static_reason adds no "nothing fires it" line; neither timer picks it up (they filter on kind)."""
    start, end = window(rec)
    flat = limits.flat_et if limits else min(end, FLAT_LATEST)
    qty = rec.get("qty")
    qty = qty if _whole(qty, 1, 10 ** 6) else 1
    fee = rec.get("commission")
    fee = float(fee) if _number(fee, 0, 1e6) else 4.0
    label = rec.get("label")
    return StrategyCfg(
        symbol=rec["root"], kind=LAB, label=label if isinstance(label, str) and label else rec["name"],
        enabled=rec.get("enabled") is True, shadow=False, metrics={},
        qty=min(qty, limits.max_qty) if limits else 1,
        offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
        cancel_et=flat, flat_et=flat,
        accept_from_et=start, accept_until_et=limits.last_entry_et if limits else flat,
        fee_rt=fee, self_fire=True)


# ------------------------------------------------------------------ what the desk holds per Lab strategy
def _meta(cfg: AppCfg) -> dict:
    """{desk id: {"name", "rec" (no source), "mark", "limits": LabLimits | None,
                  "saved": the sidecar as last read or written (no written_utc) | None,
                  "frozen": its limits did not parse: the sidecar is never written until he saves limits again,
                  "gone": the record left while a round was open, "bad": the record no longer reads,
                  "busy": a request is writing its sidecar right now}}.
    Kept ON the config object, beside its fields: asdict() and == see fields only, so it is never written and never
    compared. A config that never held a Lab strategy is not touched by a read (config.save's hook asks about every
    config that is saved)."""
    return cfg.__dict__.get("_lab") or {}


def bind(cfg: AppCfg, at) -> None:
    """Name the store this config's Lab strategies live in (None: the default one, HOMEBASE_DESKLAB_ROOT or
    ~/.homebase/desklab). persist_all, as config.save's hook, is handed only the config: it writes there."""
    cfg.__dict__["_lab_at"] = at


def _at(cfg: AppCfg, at):
    return at if at is not None else cfg.__dict__.get("_lab_at")


# ------------------------------------------------------------------ one desk owns the store
class _Lease:
    """The open desk.lock. The lock ends when this is closed, collected, or the process ends."""

    def __init__(self, fd):
        self.fd = fd

    def close(self) -> None:
        fd, self.fd = self.fd, None
        if fd is not None:
            store.desk_unlock(fd)

    def __del__(self):
        self.close()

    def __deepcopy__(self, memo):            # a copy of a config never holds (or closes) the original's lock
        return _Lease(None)

    __copy__ = lambda self: _Lease(None)     # noqa: E731


def take_store(cfg: AppCfg, at=None) -> bool:
    """Make this config's desk the ONE that writes the store's sidecars. Never waited for. A desk that does not get it
    asks again (every refresh): "busy" (another desk holds it) and "unknown" (the lock could not be tried) both end when
    the lock is free. A desk that let go (release_store: it is shutting down) never takes it back."""
    d = cfg.__dict__
    if owns(cfg):
        return True
    if d.get("_lab_store") == "released":
        return False
    try:
        fd = store.desk_lock(_at(cfg, at))
    except OSError as e:
        d["_lab_store"], d["_lab_store_error"] = "unknown", f"{type(e).__name__}: {e}"[:200]
        return False
    if fd is None:
        d["_lab_store"] = "busy"
        return False
    d["_lab_lease"], d["_lab_store"] = _Lease(fd), "owner"
    return True


def owns(cfg: AppCfg) -> bool:
    got = cfg.__dict__.get("_lab_lease")
    return got is not None and got.fd is not None


def store_state(cfg: AppCfg) -> str | None:
    """None: never asked. "owner" | "busy" (another desk holds the store) | "unknown" (the lock could not be tried) |
    "released"."""
    return cfg.__dict__.get("_lab_store")


def store_error(cfg: AppCfg) -> str | None:
    return cfg.__dict__.get("_lab_store_error")


def release_store(cfg: AppCfg) -> None:
    got = cfg.__dict__.get("_lab_lease")
    if got is not None:
        got.close()
    if cfg.__dict__.get("_lab_store") is not None:
        cfg.__dict__["_lab_store"] = "released"


# ------------------------------------------------------------------ what apply() has to say
def _note(cfg: AppCfg, event: str, **fields) -> None:
    q = cfg.__dict__.setdefault("_lab_notes", [])
    q.append((event, fields))
    del q[:-NOTES_KEPT]


def take_notes(cfg: AppCfg) -> list:
    """[(journal event, fields)] since the last call: books the desk dropped on its own, records it cannot read."""
    q = cfg.__dict__.get("_lab_notes") or []
    out = list(q)
    q.clear()
    return out


# ------------------------------------------------------------------ small reads and memory-only changes
def lab_ids(cfg: AppCfg) -> list[str]:
    return list(_meta(cfg))


def entry(cfg: AppCfg, desk_id) -> dict | None:
    """What the desk holds for one Lab strategy (see _meta); None for anything else."""
    return _meta(cfg).get(desk_id)


def is_lab(cfg: AppCfg, desk_id) -> bool:
    return desk_id in _meta(cfg)


def limits_of(cfg: AppCfg, desk_id: str) -> LabLimits | None:
    m = _meta(cfg).get(desk_id)
    return m["limits"] if m else None


def mark_of(cfg: AppCfg, desk_id: str) -> list | None:
    m = _meta(cfg).get(desk_id)
    return list(m["mark"]) if m else None


def record_of(cfg: AppCfg, desk_id: str) -> dict | None:
    """The record as the desk last read it (without its code)."""
    m = _meta(cfg).get(desk_id)
    return m["rec"] if m else None


def frozen(cfg: AppCfg, desk_id: str) -> bool:
    """Its limits were there and did not parse: no book, and its sidecar is left as it is until he saves limits again."""
    m = _meta(cfg).get(desk_id)
    return bool(m and m["frozen"])


def unreadable(cfg: AppCfg, desk_id: str) -> bool:
    """Its record no longer reads: it is kept as it last read, switched off."""
    m = _meta(cfg).get(desk_id)
    return bool(m and m["bad"])


def set_busy(cfg: AppCfg, desk_id: str, on: bool) -> None:
    m = _meta(cfg).get(desk_id)
    if m is not None:
        m["busy"] = bool(on)


def any_busy(cfg: AppCfg) -> bool:
    return any(m["busy"] for m in _meta(cfg).values())


def set_limits(cfg: AppCfg, desk_id: str, limits: LabLimits | None) -> None:
    """Memory only (persist_all writes them): the limits, and the strategy rebuilt from them."""
    m = _meta(cfg)[desk_id]
    m["limits"], m["frozen"] = limits, False
    cfg.strategies[desk_id] = strategy_cfg(m["rec"], limits)


def set_enabled(cfg: AppCfg, desk_id: str, on: bool) -> None:
    """Memory only, after the store took the switch: the page must not wait for the next read."""
    m = _meta(cfg)[desk_id]
    m["rec"] = {**m["rec"], "enabled": bool(on)}
    cfg.strategies[desk_id] = dataclasses.replace(cfg.strategies[desk_id], enabled=bool(on))   # (never raises: off is off)


def forget(cfg: AppCfg, desk_id: str) -> None:
    """Take a Lab strategy off the config (never one that is not from the Lab)."""
    if (cfg.__dict__.get("_lab") or {}).pop(desk_id, None) is not None:
        cfg.strategies.pop(desk_id, None)
        cfg.book.pop(desk_id, None)


# ------------------------------------------------------------------ the overlay
def read_store(at=None) -> dict:
    """{"records": [(record without its code, its sidecar | None)] for every record that reads,
        "files": [every name with a record FILE, whether or not it reads], "sidecars": [every name with a sidecar]}.
    The ONLY disk read of the overlay: the desk runs it in a thread. A store that cannot be listed raises (nothing may
    be concluded from it: no strategy is taken off and no sidecar removed on the strength of a failed listing)."""
    files, sides = store.names(at)
    recs = []
    for name in files:
        rec = store.get(name, at)
        if rec is not None and rec.get("name") == name:      # the file name must match the record (as store.listing)
            recs.append(({k: v for k, v in rec.items() if k != "source"}, store.get_desk(name, at)))
    return {"records": recs, "files": files, "sidecars": sides}


def _records(snap) -> list:
    return snap["records"] if isinstance(snap, dict) else list(snap)


def _files(snap) -> set:
    """Names whose record FILE is in the store. (A bare list of records, as a test may pass: those records' names.)"""
    if isinstance(snap, dict) and "files" in snap:
        return set(snap["files"])
    return {rec.get("name") for rec, _ in _records(snap) if isinstance(rec, dict)}


def _shaped(book) -> list:
    """Book rows as a sidecar holds them: {account: str, qty: whole, above 0}, one row an account. Anything else in
    the list is not a booking."""
    out, seen = [], set()
    for r in book if isinstance(book, list) else []:
        if not isinstance(r, dict):
            continue
        aid, qty = r.get("account"), r.get("qty")
        if isinstance(aid, str) and aid and aid not in seen and _whole(qty, 1, 10 ** 6):
            seen.add(aid)
            out.append({"account": aid, "qty": qty})
    return out


def _norm(mark, limits, book) -> dict:
    """A sidecar's content without its stamp: what pending() compares."""
    return {"mark": list(mark), "limits": limits,
            "book": [{"account": str(r.get("account")), "qty": int(r.get("qty") or 0)} for r in book]}


def _saved(side) -> dict | None:
    """A sidecar as read, in pending()'s shape; one that does not read in that shape equals nothing (it is rewritten)."""
    if not isinstance(side, dict):
        return None
    try:
        return _norm(side["mark"], side.get("limits"), side["book"])
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return {"unreadable": True}


def _unbook(cfg: AppCfg, did: str, rows: list, why: str) -> None:
    if rows:
        _note(cfg, "lab_unbooked", strategy=did, accounts=[r.get("account") for r in rows], why=why)


def _first(cfg: AppCfg, meta: dict, did: str, rec: dict, side) -> bool:
    """The limits and the book come from the sidecar: for a strategy the desk did not know (this once), and -- reload --
    on every read for a desk that does not own the store. Everything that can raise comes before the first change, so a
    record that cannot be read leaves nothing behind. True when its StrategyCfg changed."""
    side = side if isinstance(side, dict) else None
    mark = store.mark_of(rec)
    raw = side.get("limits") if side else None
    limits = _limits_from(raw, rec)
    s = strategy_cfg(rec, limits)
    rows = _shaped(side.get("book")) if side else []
    meta[did] = {"name": rec["name"], "rec": rec, "mark": mark, "gone": False, "bad": False, "busy": False,
                 "limits": limits, "frozen": raw is not None and limits is None, "saved": _saved(side)}
    changed = cfg.strategies.get(did) != s
    cfg.strategies[did] = s
    if rows and side.get("mark") != mark:    # the sidecar of another promotion: the accounts go, the limits stay
        _unbook(cfg, did, rows, "promoted again")
        rows = []
    if rows:
        cfg.book[did] = rows
    else:
        cfg.book.pop(did, None)
    return changed


def _known(cfg: AppCfg, m: dict, did: str, rec: dict) -> bool:
    """A strategy the desk knows: follow its record. True when its StrategyCfg changed."""
    mark = store.mark_of(rec)
    again = mark != m["mark"]
    limits, froze = m["limits"], m["frozen"]
    if again and limits is not None:         # promoted again: the limits stay only if they still fit the new record
        limits = _limits_from(asdict(limits), rec)
        froze = limits is None
    s = strategy_cfg(rec, limits)            # may raise: nothing has changed yet
    if again:
        _unbook(cfg, did, cfg.book.pop(did, None) or [], "promoted again")
        m["mark"], m["limits"], m["frozen"] = mark, limits, froze
    m["rec"], m["gone"], m["bad"] = rec, False, False
    if cfg.strategies.get(did) != s:
        cfg.strategies[did] = s
        return True
    return False


def _cannot_read(cfg: AppCfg, m: dict | None, did: str, mark, e: Exception) -> bool:
    """A record that cannot be made a strategy, or whose file does not read (mark None): said once per promotion. One
    the desk already knows is kept as it last read, switched off. True when its StrategyCfg changed."""
    said = cfg.__dict__.setdefault("_lab_said", set())
    if (did, repr(mark)) not in said:
        said.add((did, repr(mark)))
        _note(cfg, "lab_unreadable", strategy=did, mark=mark, error=f"{type(e).__name__}: {e}"[:200])
    if m is None:
        return False
    m["bad"], m["gone"] = True, False
    s = cfg.strategies.get(did)
    if s is not None and s.enabled:
        cfg.strategies[did] = dataclasses.replace(s, enabled=False)
        return True
    return False


def _enforce(cfg: AppCfg, did: str, m: dict) -> None:
    """The routes' rules over the rows of the accounts THIS desk has: no limits, no book; no row above the cap. A row
    of an account that is not in this desk's pool is not this desk's to judge: it stays exactly as it is."""
    rows = cfg.book.get(did)
    if not rows:
        return
    lim = m["limits"]
    mine = [r for r in rows if r.get("account") in cfg.accounts]
    if lim is None:
        drop, why = mine, "limits unreadable" if m["frozen"] else "no limits"
    else:
        drop, why = [r for r in mine if not _whole(r.get("qty"), 1, lim.max_qty)], "above the size cap"
    if drop:
        _unbook(cfg, did, drop, why)
        keep = [r for r in rows if r not in drop]
        if keep:
            cfg.book[did] = keep
        else:
            cfg.book.pop(did, None)


def apply(cfg: AppCfg, snap, held=None, reload: bool = False) -> dict:
    """Bring cfg.strategies / cfg.book in line with what read_store() saw. Memory only. `held(desk_id)` says whether the
    engine holds an open round for it: such a strategy is never removed (it is switched off and kept until the round
    is over). `reload`: also take the limits and the book of the strategies the desk already knows from their sidecars
    (a desk that does not own the store follows the owner's; one that just got the store starts from what is on disk)
    -- never over a change of its own that is still waiting to be written. Returns {"added": [...], "removed": [...],
    "changed": [...]} (desk ids); what else there is to say (a dropped book, a record that does not read, the accounts
    that went with a record) goes to take_notes()."""
    meta = cfg.__dict__.setdefault("_lab", {})           # the one place that starts it
    added, removed, changed, seen = [], [], [], set()
    queue = cfg.__dict__.setdefault("_lab_notes", [])
    said0 = len(queue)
    had = {did: {r.get("account") for r in cfg.book.get(did) or [] if isinstance(r, dict)} for did in meta} if reload else {}
    for rec, side in _records(snap):
        if not isinstance(rec, dict) or not isinstance(rec.get("name"), str):
            continue
        did = desk_id(rec["name"])
        seen.add(did)
        try:                                             # each record on its own: one that fails never stops the others
            if not usable(rec):
                raise ValueError("the record names no market")
            if did in meta:
                again = reload and not meta[did]["busy"] and not (owns(cfg) and pending(cfg, did))
                if _first(cfg, meta, did, rec, side) if again else _known(cfg, meta[did], did, rec):
                    changed.append(did)
            elif did not in cfg.strategies:              # (an id the desk uses for something not from the Lab is left alone)
                _first(cfg, meta, did, rec, side)
                added.append(did)
            (cfg.__dict__.get("_lab_said") or set()).discard((did, repr(None)))   # its file reads again
        except Exception as e:  # noqa: BLE001
            if _cannot_read(cfg, meta.get(did), did, store.mark_of(rec), e):
                changed.append(did)
    files = _files(snap)
    for name in sorted(files):                           # a record FILE that is there and did not read: not gone
        did = desk_id(name) if isinstance(name, str) else None
        if did is None or did in seen:
            continue
        seen.add(did)
        if _cannot_read(cfg, meta.get(did), did, None, ValueError("the record file does not read")):
            changed.append(did)
    for did in [d for d in meta if d not in seen]:       # the record is gone: its file is not in the store
        m = meta[did]
        if held is not None and held(did):
            if not m["gone"] or cfg.strategies[did].enabled:
                m["gone"], m["rec"] = True, {**m["rec"], "enabled": False}
                cfg.strategies[did] = dataclasses.replace(cfg.strategies[did], enabled=False)
                changed.append(did)
            continue
        _note(cfg, "lab_removed", strategy=did, why="record gone",
              unbooked=[r.get("account") for r in cfg.book.get(did) or [] if isinstance(r, dict)])
        forget(cfg, did)
        removed.append(did)
    for did, m in meta.items():
        _enforce(cfg, did, m)
    if reload:                                           # a reload reads every row again: say only what LEFT the desk's
        kept = []                                        # memory, not again what was dropped (and said) the first time
        for event, f in queue[said0:]:
            if event == "lab_unbooked" and f.get("strategy") in had:
                left = [a for a in f.get("accounts") or [] if a in had[f["strategy"]]]
                if not left:
                    continue
                f = {**f, "accounts": left}
            kept.append((event, f))
        queue[said0:] = kept
    cfg.__dict__["_lab_unusable"] = sorted(n for n in files if isinstance(n, str) and desk_id(n) not in meta
                                           and desk_id(n) not in cfg.strategies)
    return {"added": added, "removed": removed, "changed": changed}


def unusable(cfg: AppCfg) -> list:
    """Store names whose record file is there but is not a strategy on this desk (it does not read, or names no
    market), as of the last apply(). Remove takes them off the store: there is no dead end."""
    return list(cfg.__dict__.get("_lab_unusable") or [])


def overlay(cfg: AppCfg, at=None, *, held=None) -> dict:
    """read_store + apply in one call (the desk's start, before its loop serves anything; tests)."""
    return apply(cfg, read_store(_at(cfg, at)), held)


def orphans(cfg: AppCfg, snap, held=None) -> list:
    """Store names whose sidecar has no record FILE any more and that the desk is not holding for an open round: the
    owner removes them, so the Lab page is never left refusing Promote / Remove for a name that is no longer on the
    Desk. A record file that is there but does not read is NOT an orphan. `held(desk_id)` is asked for every name, also
    one the desk does not know (after a restart the engine may have restored a round of a strategy whose record went).
    Ask after apply() of the same read. Empty for a desk that reads only."""
    if not owns(cfg) or not isinstance(snap, dict):
        return []
    there = _files(snap)
    mine = {m["name"] for m in _meta(cfg).values()}
    return sorted(n for n in snap["sidecars"]
                  if n not in there and n not in mine and not (held is not None and held(desk_id(n))))


# ------------------------------------------------------------------ the sidecar
def sidecar(cfg: AppCfg, desk_id: str, limits: LabLimits | None, book: list) -> dict:
    """What this strategy's sidecar would hold with these limits and this book (no stamp)."""
    return _norm(_meta(cfg)[desk_id]["mark"], asdict(limits) if limits else None, book)


def commit(cfg: AppCfg, desk_id: str, limits: LabLimits | None, book: list, saved: dict | None) -> None:
    """After `saved` was written: the limits and the book become the desk's memory, in one step. saved None: nothing
    had to be written (what the desk remembers as written stays). A frozen sidecar thaws only when limits are saved."""
    m = _meta(cfg)[desk_id]
    m["limits"], m["frozen"] = limits, m["frozen"] and limits is None
    if saved is not None:
        m["saved"] = saved
    cfg.strategies[desk_id] = strategy_cfg(m["rec"], limits)
    if book or desk_id in cfg.book:          # (no rows and no key: the book stays without a key for it)
        cfg.book[desk_id] = [{"account": r["account"], "qty": int(r["qty"])} for r in book]


def pending(cfg: AppCfg, only: str | None = None) -> list:
    """[(store name, sidecar content)] for every Lab strategy (or the one named) whose sidecar is not what the desk
    holds. Memory only. Not asked of: a strategy with no limits, no account and no sidecar (nothing to say); one whose
    record is gone; one that is frozen (its sidecar is left as it is); one a request is writing right now."""
    out = []
    for did, m in _meta(cfg).items():
        if (only is not None and did != only) or m["gone"] or m["frozen"] or m["busy"]:
            continue
        want = _norm(m["mark"], asdict(m["limits"]) if m["limits"] else None, cfg.book.get(did) or [])
        if want != m["saved"] and not (m["saved"] is None and want["limits"] is None and not want["book"]):
            out.append((m["name"], want))
    return out


def stamped(want: dict) -> dict:
    return {**want, "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def persist_all(cfg: AppCfg, at=None, wait_s: float | None = 0.0) -> None:
    """Write every sidecar whose content changed (config.save's after-save hook, and the desk's refresh). Only the desk
    that owns the store writes. It never waits for the store's lock unless told to (wait_s): on a miss the sidecars stay
    pending for the next call (TimeoutError; the rest are not tried, they would miss too). Any other failure is raised
    once the others were tried. What was written and what the desk remembers as written change together, under the lock."""
    if not owns(cfg):
        return
    meta, root, first = _meta(cfg), _at(cfg, at), None
    for name, want in pending(cfg):
        try:
            with store.write_lock(root, wait_s):
                store.put_desk(name, stamped(want), root)
                meta[desk_id(name)]["saved"] = want
        except TimeoutError as e:            # the store is held: every other write would miss as well
            first = first or e
            break
        except Exception as e:  # noqa: BLE001 -- the other sidecars are still written
            first = first or e
    if first is not None:
        raise first
