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

The pieces are split so the desk can keep disk work off its event loop: read_store() is the only reader (run it in a
thread), apply() only touches memory (run it on the loop: every other reader of cfg.strategies iterates it without
awaiting), pending() only compares memory, persist_all() writes the sidecars that changed.

Nothing here runs strategy code, and nothing here is imported from homebase.backtest (tests/test_labcfg.py pins it).
Stdlib + config + the store.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import asdict, dataclass

from .config import AppCfg, StrategyCfg
from .labrun import store

LAB = "lab"                              # StrategyCfg.kind
PREFIX = "lab_"                          # desk id = PREFIX + the store name
FLAT_LATEST = "15:55"                    # version 1: flat no later than this, for every market
LOCK_WAIT_S = 0.2                        # a sidecar write gives up after this long when another process holds the store
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
    if isinstance(risk, bool) or not isinstance(risk, (int, float)) or not math.isfinite(risk) or not risk > 0:
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
    fee = float(fee) if isinstance(fee, (int, float)) and not isinstance(fee, bool) and math.isfinite(fee) and fee >= 0 else 4.0
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
    """{desk id: {"name", "rec" (no source), "mark", "limits": LabLimits | None, "saved": the sidecar as last read or
    written (no written_utc) | None, "gone": the record left while a round was open}}. Kept ON the config object, beside
    its fields: asdict() and == see fields only, so it is never written and never compared."""
    m = cfg.__dict__.get("_lab")
    if m is None:
        m = cfg.__dict__["_lab"] = {}
    return m


def lab_ids(cfg: AppCfg) -> list[str]:
    return list(_meta(cfg))


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


def set_limits(cfg: AppCfg, desk_id: str, limits: LabLimits | None) -> None:
    """Memory only (persist_all writes them): the limits, and the strategy rebuilt from them."""
    m = _meta(cfg)[desk_id]
    m["limits"] = limits
    cfg.strategies[desk_id] = strategy_cfg(m["rec"], limits)


def set_enabled(cfg: AppCfg, desk_id: str, on: bool) -> None:
    """Memory only, after the store took the switch: the page must not wait for the next read."""
    m = _meta(cfg)[desk_id]
    m["rec"] = {**m["rec"], "enabled": bool(on)}
    cfg.strategies[desk_id] = strategy_cfg(m["rec"], m["limits"])


def forget(cfg: AppCfg, desk_id: str) -> None:
    """Take a Lab strategy off the config (never one that is not from the Lab)."""
    if _meta(cfg).pop(desk_id, None) is not None:
        cfg.strategies.pop(desk_id, None)
        cfg.book.pop(desk_id, None)


# ------------------------------------------------------------------ the overlay
def read_store(at=None) -> list:
    """[(record without its code, its sidecar | None)] for every promoted strategy the desk can use. The ONLY disk read
    of the overlay: the desk runs it in a thread."""
    out = []
    for rec in store.listing(at):
        if usable(rec):
            out.append(({k: v for k, v in rec.items() if k != "source"}, store.get_desk(rec["name"], at)))
    return out


def _rows(book, cfg: AppCfg) -> list:
    """Book rows as a sidecar holds them, kept only for accounts on the desk with a size above 0, one row an account."""
    out, seen = [], set()
    for r in book if isinstance(book, list) else []:
        if not isinstance(r, dict):
            continue
        aid, qty = r.get("account"), r.get("qty")
        if isinstance(aid, str) and aid in cfg.accounts and aid not in seen and _whole(qty, 1, 10 ** 6):
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
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"unreadable": True}


def apply(cfg: AppCfg, snap: list, held=None) -> dict:
    """Bring cfg.strategies / cfg.book in line with what read_store() saw. Memory only. `held(desk_id)` says whether the
    engine holds an open round for it: such a strategy is never removed (it is switched off and kept until the round
    is over). Returns {"added": [...], "removed": [...], "changed": [...]} (desk ids)."""
    meta = _meta(cfg)
    added, removed, changed, seen = [], [], [], set()
    for rec, side in snap:
        did = desk_id(rec["name"])
        seen.add(did)
        mark = store.mark_of(rec)
        m = meta.get(did)
        if m is None:
            if did in cfg.strategies:                    # an id the desk already uses for something not from the Lab
                continue
            side = side if isinstance(side, dict) else None
            same = side is not None and side.get("mark") == mark
            book = _rows(side.get("book"), cfg) if same else []
            m = meta[did] = {"name": rec["name"], "rec": rec, "mark": mark, "gone": False,
                             "limits": _limits_from(side.get("limits"), rec) if side else None, "saved": _saved(side)}
            cfg.strategies[did] = strategy_cfg(rec, m["limits"])
            if book:
                cfg.book[did] = book
            else:
                cfg.book.pop(did, None)
            added.append(did)
            continue
        if mark != m["mark"]:                            # promoted again: the accounts go, the limits stay if they still fit
            cfg.book.pop(did, None)
            m["mark"] = mark
            if m["limits"] is not None:
                m["limits"] = _limits_from(asdict(m["limits"]), rec)
        m["rec"], m["gone"] = rec, False
        s = strategy_cfg(rec, m["limits"])
        if cfg.strategies.get(did) != s:
            cfg.strategies[did] = s
            changed.append(did)
    for did in [d for d in meta if d not in seen]:       # the record is gone
        if held is not None and held(did):
            m = meta[did]
            if not m["gone"] or cfg.strategies[did].enabled:
                m["gone"], m["rec"] = True, {**m["rec"], "enabled": False}
                cfg.strategies[did] = strategy_cfg(m["rec"], m["limits"])
                changed.append(did)
            continue
        forget(cfg, did)
        removed.append(did)
    return {"added": added, "removed": removed, "changed": changed}


def overlay(cfg: AppCfg, at=None, *, held=None) -> dict:
    """read_store + apply in one call (the desk's start, before its loop serves anything; tests)."""
    return apply(cfg, read_store(at), held)


# ------------------------------------------------------------------ the sidecar
def pending(cfg: AppCfg) -> list:
    """[(store name, sidecar content)] for every Lab strategy whose sidecar is not what the desk holds. Memory only. A
    strategy with no limits, no account and no sidecar has nothing to say: none is written. One whose record is gone is
    left as it is on disk."""
    out = []
    for did, m in _meta(cfg).items():
        if m["gone"]:
            continue
        want = _norm(m["mark"], asdict(m["limits"]) if m["limits"] else None, cfg.book.get(did) or [])
        if want != m["saved"] and not (m["saved"] is None and want["limits"] is None and not want["book"]):
            out.append((m["name"], want))
    return out


def persist_all(cfg: AppCfg, at=None, wait_s: float | None = LOCK_WAIT_S) -> None:
    """Write every sidecar whose content changed (config.save's after-save hook, and the desk's own calls). A write that
    fails is not forgotten: it stays pending for the next call, and the first error is raised once the others were tried.
    Small files, written whole; the wait for the store's lock is bounded, so the desk's loop never stands still on it."""
    meta, first = _meta(cfg), None
    for name, want in pending(cfg):
        try:
            store.put_desk(name, {**want, "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
                           at, wait_s=wait_s)
            meta[desk_id(name)]["saved"] = want
        except Exception as e:  # noqa: BLE001 -- the other sidecars are still written
            first = first or e
    if first is not None:
        raise first
