"""The chart's journal: a Desk day's round trips, with a note and tags on each.

Read-only on the desk's journal.jsonl (never opened for writing, never locked). The desk journals a bot's entry and exit, but
a chart (manual) trade's broker fills are not in it, so this service also logs the fills the desk link publishes, one file per
Desk day, in its own state folder: <state>/journal/fills/<day>.jsonl. Notes and tags go to <state>/journal/notes.json, never
into the engine's journal. A round trip is flat to flat on one account and one contract; $ is gross (no fees).
shortcut: a trip pairs inside one Desk day, so a position held across 18:00 ET shows as two open trips; upgrade by pairing
from the day before when that matters."""
from __future__ import annotations

import datetime as dt
import json
import math
import threading
import time
from pathlib import Path

from ..contracts import point_value, root_of
from ..core import atomic
from ..core.session import ET
from . import _jsonl

STOP_SLACK_MS = 5000       # the journal line of an order lands just after its fill can: a stop sent up to 5 s later still counts
MAX_NOTE, MAX_TAGS, MAX_TAG, MAX_KEY = 2000, 8, 24, 120


def _day(t: dt.datetime) -> str:
    return (t.date() + dt.timedelta(days=t.hour >= 18)).isoformat()      # the Desk day starts at 18:00 ET


def desk_day_of_ms(ms: int) -> str:
    return _day(dt.datetime.fromtimestamp(ms / 1000, ET))


def desk_day_of_et(et) -> str:
    """The Desk day of a journal `et` string; "" when it cannot be read."""
    try:
        return _day(dt.datetime.fromisoformat(str(et)))
    except ValueError:
        return ""


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def read_journal(path: Path, day: str) -> list[dict]:
    """The desk journal's records of one Desk day. A missing or unreadable file, a torn or non-object line: skipped."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and desk_day_of_et(rec.get("et")) == day:
                    out.append(rec)
    except OSError:
        pass
    return out


# ---- the fill log -----------------------------------------------------------------------------------------------
def _fill_ms(raw) -> int:
    try:
        return int(dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000)


def record_fill(fills_dir: Path, msg) -> None:
    """Log one desk 'fill' message ({"type": "desk", "event": "fill", "data": {"account", "fill"}}). Never raises: the desk
    relay must not care whether the log worked."""
    try:
        if not isinstance(msg, dict) or msg.get("event") != "fill":
            return
        data = msg.get("data")
        f = data.get("fill") if isinstance(data, dict) else None
        if not isinstance(f, dict) or not isinstance(data.get("account"), str):
            return
        qty, price = _num(f.get("qty")), _num(f.get("price"))
        if not qty or qty <= 0 or price is None or f.get("side") not in ("Buy", "Sell") or f.get("id") is None:
            return
        ms = _fill_ms(f.get("time"))
        fills_dir.mkdir(parents=True, exist_ok=True)
        _jsonl.append(fills_dir / f"{desk_day_of_ms(ms)}.jsonl",
                      {"ms": ms, "account": data["account"], "id": f["id"], "order_id": f.get("order_id"),
                       "symbol": f.get("symbol"), "side": f["side"], "qty": qty, "price": price, "owner": f.get("owner")})
    except Exception:  # noqa: BLE001
        pass


def record_carried(fills_dir: Path, msg, now_ms: int) -> None:
    """The log starts late when the chart service restarts with a position open: its exit would then show as a trip the
    other way. On a desk 'state' message, log a position the log has no fills for as one Buy/Sell at the account's average
    price, so the exit closes it. Never raises."""
    try:
        if not isinstance(msg, dict) or msg.get("event") != "state":
            return                                  # a state is rare (a connect or resync); a fill never reads the log here
        accounts = msg["data"]["accounts"]
        path = fills_dir / f"{desk_day_of_ms(now_ms)}.jsonl"
        known = {(f.get("account"), f.get("symbol")) for f in _jsonl.read_all(path)}
        for a in accounts if isinstance(accounts, list) else []:
            for p in a.get("positions") or []:
                net, price = _num(p.get("net")), _num(p.get("avg_price"))
                if not net or price is None or not isinstance(p.get("symbol"), str) or (a.get("id"), p["symbol"]) in known:
                    continue
                fills_dir.mkdir(parents=True, exist_ok=True)
                _jsonl.append(path, {"ms": now_ms, "account": a["id"], "id": f"carried-{now_ms}-{p['symbol']}", "order_id": None,
                                     "symbol": p["symbol"], "side": "Buy" if net > 0 else "Sell", "qty": abs(net), "price": price,
                                     "owner": None})
                known.add((a["id"], p["symbol"]))
    except Exception:  # noqa: BLE001
        pass


def read_fills(fills_dir: Path, day: str) -> list[dict]:
    """The logged fills of a Desk day, once each (the desk repeats a notice after a resync)."""
    seen, out = set(), []
    for f in _jsonl.read_all(fills_dir / f"{day}.jsonl"):
        k = (f.get("account"), f.get("id"))
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


# ---- round trips ------------------------------------------------------------------------------------------------
def _trip(account, symbol, owner, d, entries, exits, left) -> dict:
    eq = sum(q for q, _, _ in entries)
    entry = sum(q * p for q, p, _ in entries) / eq
    t = {"id": f"{account}|{symbol}|{entries[0][2]}", "account": account, "symbol": symbol, "owner": owner,
         "side": "Buy" if d > 0 else "Sell", "qty": left or eq, "entry": entry, "entry_ms": entries[0][2], "exit": None,
         "exit_ms": None, "pnl": None, "stop": None, "r": None, "open": left > 0, "left": left, "source": "fills"}
    if not left:
        xq = sum(q for q, _, _ in exits)
        t["exit"], t["exit_ms"] = sum(q * p for q, p, _ in exits) / xq, exits[-1][2]
        pv = point_value(symbol)
        t["pnl"] = None if pv is None else d * (t["exit"] - entry) * eq * pv
    return t


def round_trips(fills: list) -> list[dict]:
    """Flat-to-flat trips from fills ({ms, account, symbol, side, qty, price, owner}), oldest first. A fill that crosses
    zero closes the old trip with its first part and opens the next with the rest."""
    clean = []
    for f in fills:
        if not isinstance(f, dict):
            continue
        qty, price, ms = _num(f.get("qty")), _num(f.get("price")), _num(f.get("ms"))
        if not qty or qty <= 0 or price is None or ms is None or f.get("side") not in ("Buy", "Sell"):
            continue
        clean.append((int(ms), str(f.get("account")), str(f.get("symbol")), 1 if f["side"] == "Buy" else -1, qty, price,
                      f.get("owner")))
    clean.sort(key=lambda c: c[0])         # stable: fills of one millisecond keep the order they were logged in
    book: dict = {}            # (account, symbol) -> [dir, entries, exits, net, owner]
    out = []
    for ms, acct, sym, sgn, qty, price, owner in clean:
        while qty > 0:
            b = book.setdefault((acct, sym), [0, [], [], 0.0, owner])
            if b[3] == 0:
                b[:] = [sgn, [], [], 0.0, owner]
            if sgn == b[0]:
                b[1].append((qty, price, ms))
                b[3] += qty
                qty = 0
            else:
                take = min(qty, b[3])
                b[2].append((take, price, ms))
                b[3] -= take
                qty -= take
                if b[3] == 0:
                    out.append(_trip(acct, sym, b[4], b[0], b[1], b[2], 0))
    for (acct, sym), b in book.items():
        if b[3] > 0:
            out.append(_trip(acct, sym, b[4], b[0], b[1], b[2], b[3]))
    return sorted(out, key=lambda t: t["entry_ms"])


def _r(t: dict) -> None:
    """R = the trip's points / the points risked to its stop. A stop on the wrong side of the entry is no stop."""
    d = 1 if t["side"] == "Buy" else -1
    if t["stop"] is None or d * (t["entry"] - t["stop"]) <= 0:
        t["stop"] = t["r"] = None
    elif t["exit"] is not None:
        t["r"] = d * (t["exit"] - t["entry"]) / (d * (t["entry"] - t["stop"]))


def attach_stops(trips: list[dict], records: list) -> None:
    """Give each fills trip the stop of the last accepted chart order that opened it (same account, contract and side,
    sent before its first fill, one order for one trip), and its R. No such order, or one sent without a stop: no stop, no R.
    shortcut: a scale-in order sent after the first fill is not matched to its trip, upgrade when that matters."""
    orders = [r for r in records if isinstance(r, dict) and r.get("event") == "manual_order" and r.get("ok") is True
              and _num(r.get("ts")) is not None]
    orders.sort(key=lambda r: r["ts"])
    used = set()
    for t in trips:
        if t["source"] != "fills":
            continue
        for i in range(len(orders) - 1, -1, -1):
            r = orders[i]
            if (i not in used and r.get("account") == t["account"] and r.get("side") == t["side"]
                    and root_of(r.get("contract") or r.get("root")) == root_of(t["symbol"])
                    and r["ts"] * 1000 <= t["entry_ms"] + STOP_SLACK_MS):
                used.add(i)
                sl = _num(r.get("sl"))              # an order without a stop still opened this trip: it must not borrow an older one
                t["stop"] = sl
                break
        _r(t)


def bot_trips(records: list) -> list[dict]:
    """A bot's runs from the journal's entry_fill / brackets_moved / exit_fill lines, for days the fill log has nothing for.
    The journal names no contract: the trip carries the strategy as its owner, and the $ is the engine's own gross P&L."""
    open_: dict = {}
    out = []
    for r in sorted((r for r in records if isinstance(r, dict) and _num(r.get("ts")) is not None), key=lambda r: r["ts"]):
        k = (r.get("account"), r.get("strategy"))
        ev, ms = r.get("event"), int(r["ts"] * 1000)
        if ev == "entry_fill" and _num(r.get("fill")) is not None and r.get("side") in ("Buy", "Sell"):
            t = open_.get(k) or {"id": f"{k[0]}|{k[1]}|{ms}", "account": k[0], "symbol": "", "owner": k[1], "side": r["side"],
                                 "entry_ms": ms, "exit": None, "exit_ms": None, "pnl": None, "stop": None, "r": None,
                                 "open": True, "left": 0, "source": "journal"}
            t["entry"], t["qty"] = float(r["fill"]), _num(r.get("qty_filled")) or 1.0     # later lines carry the average
            open_[k] = t
        elif k in open_ and ev == "brackets_moved" and _num(r.get("sl")) is not None:
            open_[k]["stop"] = float(r["sl"])
        elif k in open_ and ev == "exit_fill" and _num(r.get("fill")) is not None:
            t = open_.pop(k)
            t.update(exit=float(r["fill"]), exit_ms=ms, pnl=_num(r.get("pnl")), open=False)
            _r(t)
            out.append(t)
    for t in open_.values():
        t["stop"] = t["r"] = None
        out.append(t)
    return sorted(out, key=lambda t: t["entry_ms"])


def day_trips(journal_path: Path, fills_dir: Path, day: str) -> list[dict]:
    """A Desk day's trips: from the fill log for every account it has fills for, from the journal's bot lines for the rest."""
    recs = read_journal(journal_path, day)
    fills = read_fills(fills_dir, day)
    trips = round_trips(fills)
    attach_stops(trips, recs)
    logged = {f.get("account") for f in fills}
    trips += [t for t in bot_trips(recs) if t["account"] not in logged]
    return sorted(trips, key=lambda t: t["entry_ms"])


# ---- notes and tags ---------------------------------------------------------------------------------------------
class Notes:
    """{trip id: {note, tags}} in one JSON file, written whole through a temp file. One lock: two saves never lose each other."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def all(self) -> dict:
        try:
            v = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}

    def put(self, key, note, tags) -> None:
        """Save a trip's note and tags; empty ones remove the entry. ValueError (shown to the page) on anything malformed."""
        if not isinstance(key, str) or not 1 <= len(key) <= MAX_KEY or any(ord(c) < 32 for c in key):
            raise ValueError("id: 1-120 characters")
        if not isinstance(note, str) or len(note) > MAX_NOTE:
            raise ValueError(f"note: text of at most {MAX_NOTE} characters")
        if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(isinstance(t, str) and len(t) <= MAX_TAG for t in tags):
            raise ValueError(f"tags: at most {MAX_TAGS} words of at most {MAX_TAG} characters")
        clean = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        with self._lock:
            data = self.all()
            if note.strip() or clean:
                data[key] = {"note": note, "tags": clean}
            else:
                data.pop(key, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(self.path, json.dumps(data, indent=2))
