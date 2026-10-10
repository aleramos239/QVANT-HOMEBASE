"""A bot's past runs, rebuilt from the desk journal (<state>/journal.jsonl).

Pure: records in, runs out. One run per (date, account) the strategy acted
on; a day it never reached an account (a gate-chop skip, a refused alert, a
kill before the fire) is one run with account None, meaning every booked
account. Statuses: traded | skipped | refused | no_fill | killed | error.

  legs        the entry orders it placed ({side, price, ts})
  entry       {side, price, ts, slip_ticks}: the (average) entry fill; slip_ticks
              is the fill vs its stop trigger (the matching leg), signed so
              positive = worse for us; null when it can't be computed
  exit        {price, ts, kind}: kind tp | sl from the engine's grade, "flat" when
              a flatten closed it (15:55 clock, a kill, a manual flatten), else
              "other". An "sl" exit also carries slip_ticks (vs the SL price
              from the engine's brackets_moved re-price, same sign convention)
              and gap_through (true when that slip is >= 2 ticks)
  pnl_usd     (exit - entry) x side x point value x qty, less $4 per contract per
              round trip; left out when the fills cannot be matched
  fire_ms     09:30:00.000 ET on the run's date (the self-timer's fixed fire
              time); placed_ms is the journal ts of "placed"; latency_ms is
              their difference. Present whenever a "placed" landed, else left
              out entirely

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
from zoneinfo import ZoneInfo

from .contracts import point_value, tick_size

COMMISSION_RT = 4.0              # $ per contract per round trip
DAYS_DEFAULT, DAYS_MAX = 120, 400
KILLED_FROM_CHART = "killed from the chart"
_IGNORED_REFUSALS = {"already_traded"}      # a late second signal on a day it acted: noise
_FLAT_EVENTS = {"clock_flat", "manual_flatten"}

ET = ZoneInfo("America/New_York")
FIRE_ET = dt.time(9, 30, 0)      # the self-timer's fixed fire time; no per-strategy
                                  # fire time exists in the journal or config today
GAP_THROUGH_TICKS = 2.0          # an SL fill this far beyond its stop counts as a gap
_TICK_EPS = 1e-9


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


def _fire_ms(date: str) -> Optional[int]:
    """09:30:00.000 ET on this run's date, as epoch ms (DST-correct)."""
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        return None
    return int(dt.datetime.combine(d, FIRE_ET, tzinfo=ET).timestamp() * 1000)


def _trigger_price(legs: list[dict], side) -> Optional[float]:
    for leg in legs:
        if leg.get("side") == side:
            return leg.get("price")
    return None


def _entry_slip_ticks(entry: dict, legs: list[dict], tick: float) -> Optional[float]:
    """Entry fill vs its stop trigger, in ticks, signed so positive = worse for us."""
    side = entry.get("side")
    if side not in ("Buy", "Sell") or not tick:
        return None
    trigger, fill = _trigger_price(legs, side), entry.get("price")
    if trigger is None or fill is None:
        return None
    sign = 1 if side == "Buy" else -1
    return round(sign * (fill - trigger) / tick, 4) + 0.0     # no signed zero


def _exit_slip_ticks(entry: Optional[dict], exit_price: Optional[float],
                     sl_ref: Optional[float], tick: float) -> Optional[float]:
    """An SL exit fill vs its stop price, in ticks, signed so positive = worse for us."""
    side = entry.get("side") if entry else None
    if side not in ("Buy", "Sell") or not tick or sl_ref is None or exit_price is None:
        return None
    sign = 1 if side == "Buy" else -1
    return round(sign * (sl_ref - exit_price) / tick, 4) + 0.0   # no signed zero


def runs(records: Iterable[dict], strategy: str, *, symbol: str, today: str,
         days: int = DAYS_DEFAULT) -> list[dict]:
    first = (dt.date.fromisoformat(today) - dt.timedelta(days=days - 1)).isoformat()
    tick = tick_size(symbol)
    acct: dict[tuple, dict] = {}          # (date, account) -> working run
    day: dict[str, dict] = {}             # date -> strategy-level facts (no account)
    earlier: list[tuple] = []             # ((date, account), run): a Lab strategy's rounds before the one in `acct`

    def run_of(date, account) -> dict:
        return acct.setdefault((date, account), {"legs": [], "qty": None, "entry": None,
                                                 "exit": None, "flat": False, "status": None,
                                                 "reason": None, "killed": False,
                                                 "resolved": False, "sl_ref": None})

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
        if ev == "lab_round" and account:
            # a Lab strategy trades in rounds, several a day on one account: this line starts a new run, and the
            # one before it (when there is one) is over. Every other kind never writes it.
            if (date, account) in acct:
                earlier.append(((date, account), acct.pop((date, account))))
            run_of(date, account)["round"] = rec.get("round")
        elif ev == "placed" and account:
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
        elif ev == "brackets_moved" and account:
            # the stop that's actually working, re-priced to the real fill
            # (engine._move_brackets); a fill at the trigger leaves it here too
            r = run_of(date, account)
            sl = _num(rec.get("sl"))
            if sl is not None:
                r["sl_ref"] = sl
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
    for (date, account), r in earlier + list(acct.items()):
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
        if "round" in r:         # a Lab round: which one it was. It is not the 09:30 fire: no fire_ms, no latency_ms
            row["round"] = r["round"]
            if r["legs"]:
                row["placed_ms"] = r["legs"][0]["ts"]
        elif r["legs"]:          # a "placed" landed: the fire-to-ack latency applies
            fire_ms, placed_ms = _fire_ms(date), r["legs"][0]["ts"]
            row["fire_ms"] = fire_ms
            row["placed_ms"] = placed_ms
            row["latency_ms"] = (placed_ms - fire_ms if fire_ms is not None
                                 and placed_ms is not None else None)
        if entry is not None:
            row["entry"] = {**entry, "slip_ticks": _entry_slip_ticks(entry, r["legs"], tick)}
        if ex is not None:
            exit_row = {**ex, "kind": "flat"} if r["flat"] else dict(ex)
            if exit_row.get("kind") == "sl":
                slip = _exit_slip_ticks(entry, exit_row.get("price"), r["sl_ref"], tick)
                exit_row["slip_ticks"] = slip
                exit_row["gap_through"] = (None if slip is None else
                                           slip >= GAP_THROUGH_TICKS - _TICK_EPS)
            row["exit"] = exit_row
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
