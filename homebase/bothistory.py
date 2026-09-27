"""A bot's past runs, rebuilt from the desk journal (<state>/journal.jsonl).

Pure: records in, runs out. One run per (date, account) the strategy acted
on; a day it never reached an account (a gate-chop skip, a refused alert, a
kill before the fire) is one run with account None, meaning every booked
account. Statuses: traded | skipped | refused | no_fill | killed | error.

  legs    the entry orders it placed ({side, price, ts})
  entry   {side, price, ts}: the (average) entry fill
  exit    {price, ts, kind}: kind tp | sl from the engine's grade, "flat" when
          a flatten closed it (15:55 clock, a kill, a manual flatten), else
          "other"
  pnl_usd (exit - entry) x side x point value x qty, less $4 per contract per
          round trip; left out when the fills cannot be matched

ts values are epoch milliseconds. Today's run is left out until it has a
result (an entry, a cancel, a skip, ...). A kill (the chart's per-bot
Kill, or the desk's Kill) marks a run killed only if it has no exit yet: a
finished trade keeps its real exit. Malformed journal lines (and a
non-string account) are skipped. JournalCache parses only the bytes appended
since the last read (a full re-read only when the file shrank or was
replaced); the desk calls it in a thread (asyncio.to_thread)."""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Iterable, Optional

from .contracts import point_value

COMMISSION_RT = 4.0              # $ per contract per round trip
DAYS_DEFAULT, DAYS_MAX = 120, 400
KILLED_FROM_CHART = "killed from the chart"
_IGNORED_REFUSALS = {"already_traded"}      # a late second signal on a day it acted: noise
_FLAT_EVENTS = {"clock_flat", "manual_flatten"}


def parse_days(v) -> int:
    """The `days` query value: None -> 120; else a whole number 1-400
    (an int, or its decimal string as a query string carries it)."""
    if v is None:
        return DAYS_DEFAULT
    if isinstance(v, str) and v.isdigit():
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= DAYS_MAX:
        raise ValueError(f"days: a whole number 1-{DAYS_MAX}")
    return v


def parse_lines(lines: Iterable[str]) -> list[dict]:
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


class JournalCache:
    """The journal's records, parsed incrementally: each call reads only the
    complete lines appended since the last one (the journal is append-only).
    The file shrinking, being replaced (another inode) or changing without
    growing -> one full re-read. Unchanged (size, mtime) -> no read at all."""

    def __init__(self):
        self._ident: Optional[tuple] = None   # (path, inode)
        self._off = 0                         # bytes parsed so far (always a line end)
        self._stamp: Optional[tuple] = None   # (size, mtime_ns) at the last call
        self._recs: list[dict] = []
        self._lock = threading.Lock()        # called from worker threads (asyncio.to_thread)

    @staticmethod
    def _read_from(path: Path, offset: int, size: int) -> bytes:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read(size - offset)

    def records(self, path: Path) -> list[dict]:
        with self._lock:
            try:
                st = path.stat()
            except OSError:
                return []
            stamp = (st.st_size, st.st_mtime_ns)
            if stamp == self._stamp and self._ident == (str(path), st.st_ino):
                return self._recs
            if self._ident != (str(path), st.st_ino) or st.st_size < self._off \
                    or (self._stamp is not None and st.st_size == self._stamp[0]):
                self._ident, self._off, self._recs = (str(path), st.st_ino), 0, []
            if st.st_size > self._off:
                try:
                    chunk = self._read_from(path, self._off, st.st_size)
                except OSError:
                    return []
                end = chunk.rfind(b"\n")
                if end >= 0:                  # only whole lines; a partial tail waits
                    new = parse_lines(chunk[:end].decode("utf-8", errors="replace").splitlines())
                    self._recs = self._recs + new     # a new list: a reader's copy never changes
                    self._off += end + 1
            self._stamp = stamp
            return self._recs


def _ms(rec: dict) -> Optional[int]:
    ts = rec.get("ts")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        return int(round(ts * 1000))
    return None


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def runs(records: Iterable[dict], strategy: str, *, symbol: str, today: str,
         days: int = DAYS_DEFAULT) -> list[dict]:
    first = (dt.date.fromisoformat(today) - dt.timedelta(days=days - 1)).isoformat()
    acct: dict[tuple, dict] = {}          # (date, account) -> working run
    day: dict[str, dict] = {}             # date -> strategy-level facts (no account)

    def run_of(date, account) -> dict:
        return acct.setdefault((date, account), {"legs": [], "qty": None, "entry": None,
                                                 "exit": None, "flat": False, "status": None,
                                                 "reason": None, "killed": False,
                                                 "resolved": False})

    def killed(date, account) -> None:
        """A kill ends only a run still going: one that already exited keeps its real exit."""
        r = run_of(date, account)
        if r["exit"] is None:
            r["killed"] = r["flat"] = r["resolved"] = True

    for rec in records:
        et, ev = rec.get("et"), rec.get("event")
        if not isinstance(et, str) or len(et) < 10 or not isinstance(ev, str):
            continue
        date = et[:10]
        if not first <= date <= today:
            continue
        if ev == "kill_switch":
            for key in (rec.get("strategies") or {}) if isinstance(rec.get("strategies"), dict) else ():
                name, _, account = str(key).partition("@")
                if name == strategy and account:
                    killed(date, account)
            continue
        if rec.get("strategy") != strategy:
            continue
        account = rec.get("account")
        if account is not None and not isinstance(account, str):
            continue                                   # malformed: never a dict key
        ts = _ms(rec)
        if ev == "placed" and account:
            r = run_of(date, account)
            r["qty"] = _num(rec.get("qty"))
            if "upper" in rec or "lower" in rec:           # a straddle: both entry stops
                r["legs"] = [{"side": s, "price": _num(rec.get(k)), "ts": ts}
                             for s, k in (("Buy", "upper"), ("Sell", "lower")) if k in rec]
            else:                                          # a bars rule: one bracketed leg
                px = rec.get("ref_px") if rec.get("ref_px") is not None else rec.get("entry_price")
                r["legs"] = [{"side": rec.get("side"), "price": _num(px), "ts": ts}]
        elif ev == "entry_fill" and account:
            r = run_of(date, account)
            prev = r["entry"]
            r["entry"] = {"side": rec.get("side"), "price": _num(rec.get("fill")),
                          "ts": prev["ts"] if prev else ts}   # the first fill's time, the average price
            if _num(rec.get("qty_filled")):
                r["qty"] = _num(rec.get("qty_filled"))
            r["resolved"] = True
        elif ev == "exit_fill" and account:
            r = run_of(date, account)
            kind = rec.get("reason") if rec.get("reason") in ("tp", "sl") else "other"
            r["exit"] = {"price": _num(rec.get("fill")), "ts": ts, "kind": kind}
            r["resolved"] = True
        elif ev in _FLAT_EVENTS:
            targets = [account] if account else \
                [a for a in (rec.get("results") or {})] if isinstance(rec.get("results"), dict) else []
            for a in targets:
                r = run_of(date, a)
                r["flat"] = r["resolved"] = True
        elif ev == "cancelled_unfilled" and account:
            r = run_of(date, account)
            r["status"], r["resolved"] = r["status"] or "no_fill", True
        elif ev == "place_failed" and account:
            r = run_of(date, account)
            r["status"], r["reason"], r["resolved"] = "error", rec.get("error"), True
        elif ev == "both_filled_emergency" and account:
            r = run_of(date, account)
            r["status"], r["reason"], r["resolved"] = "error", "both_filled", True
        elif ev == "timer_skipped":
            if account:
                r = run_of(date, account)
                r["status"], r["reason"], r["resolved"] = "skipped", rec.get("reason"), True
            else:
                day.setdefault(date, {}).setdefault("skipped", rec.get("reason"))
        elif ev in ("alert_refused", "signal_refused") and not account:
            if rec.get("reason") not in _IGNORED_REFUSALS:
                day.setdefault(date, {}).setdefault("refused", rec.get("reason"))
        elif ev == "strategy_killed_after_ack" and account:     # killed while placing
            killed(date, account)
        elif ev == "strategy_kill_requested":
            day.setdefault(date, {})["killed"] = True
        elif ev == "strategy_killed":
            day.setdefault(date, {})["killed"] = True
            results = rec.get("results") if isinstance(rec.get("results"), dict) else {}
            for a, res in results.items():
                if isinstance(res, dict) and res.get("acted"):    # it ended a running run there
                    killed(date, a)

    out = []
    for (date, account), r in acct.items():
        if not r["resolved"]:
            if date == today:
                continue                               # still running: no result yet
            if r["legs"]:
                r["status"] = "no_fill"                # placed, never filled, day over
            else:
                continue
        entry, ex = r["entry"], r["exit"]
        if r["killed"]:
            status = "killed"
        elif r["status"] == "error":
            status = "error"
        elif entry is not None:
            status = "traded"
        else:
            status = r["status"] or "no_fill"
        row = {"date": date, "account": account, "status": status}
        if status in ("error", "skipped") and r["reason"] is not None:
            row["reason"] = r["reason"]
        row["legs"] = r["legs"]
        if entry is not None:
            row["entry"] = entry
        if ex is not None:
            row["exit"] = {**ex, "kind": "flat"} if r["flat"] else ex
        pnl = _pnl(entry, ex, r["qty"], symbol)
        if pnl is not None:
            row["pnl_usd"] = pnl
        out.append(row)

    dated = {d for d, _ in acct if any(row["date"] == d for row in out)}
    for date, facts in day.items():
        if date in dated:
            continue                                   # the accounts' own runs say it all
        if facts.get("killed"):
            status, reason = "killed", KILLED_FROM_CHART
        elif "skipped" in facts:
            status, reason = "skipped", facts["skipped"]
        elif "refused" in facts:
            status, reason = "refused", facts["refused"]
        else:
            continue
        out.append({"date": date, "account": None, "status": status, "reason": reason, "legs": []})
    out.sort(key=lambda row: (row["date"], "" if row["account"] is None else str(row["account"])))
    return out


def _pnl(entry, ex, qty, symbol) -> Optional[float]:
    if not entry or not ex or not qty:
        return None
    e, x = entry.get("price"), ex.get("price")
    pv = point_value(symbol)
    if e is None or x is None or pv is None or entry.get("side") not in ("Buy", "Sell"):
        return None
    sign = 1 if entry["side"] == "Buy" else -1
    return round(sign * (x - e) * pv * qty - COMMISSION_RT * qty, 2)
