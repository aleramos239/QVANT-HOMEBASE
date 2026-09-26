# VENDORED from ONYX TRADING onyx/report/ledger.py at commit 338b969 (git -C "/Users/ramoscapital/ONYX TRADING" show 338b969:onyx/report/ledger.py).
# Do not edit here: re-vendor instead. Stdlib only.
"""Normalize any trade log this repo produces into one canonical row shape.

Every report and every prop sim reads ``Trade`` rows and nothing else, so a
TradingView export, a research-script ledger and a DSL-engine run all grade on
identical math.

Canonical row (``Trade``):
    entry_ts / exit_ts   epoch seconds, UTC (exit_ts falls back to entry_ts)
    side                 "long" | "short"
    qty                  contracts, or None when the source did not record it
    pnl                  realized USD, NET of whatever costs the source applied
    runup / drawdown     peak favorable / adverse USD excursion while open,
                         or None when the source did not record it
    risk                 USD risked on the trade (stop distance x qty x point
                         value), or None — only sources that record a stop can
                         fill this, and only they can be re-sized by --risk.
    cost                 USD of friction ALREADY subtracted from ``pnl`` (the
                         1x rung), or None. Read from a commission column, or
                         supplied via ``apply_cost``. Only trades that know
                         this can be put on a cost ladder.

Supported sources (auto-detected by ``load``):

1. **TradingView export CSV** — ``tools/tvbt.py``'s ``write_trades_csv`` and the
   ``runs/*.csv`` files: header ``entry_time,entry_price,entry_id,exit_time,
   exit_price,exit_id,qty,profit,...,runup,drawdown,commission``. Side comes
   from ``entry_id`` ("L"/"S" prefix, or the words long/short/buy/sell).
1b. **TradingView "List of trades" UI export** — two rows per trade (an ``Entry``
   and an ``Exit``, keyed by ``Trade number``/``Trade #``). Newer exports repeat
   the trade-level ``Net PnL USD`` and ``Commission USD`` on BOTH rows, so
   loading them row-per-trade doubles every number. ``_pair_entry_exit``
   collapses each pair into one row before the alias table runs.
2. **Generic trade CSV** — any CSV carrying a P&L column (``pnl``/``profit``/
   ``pnl_usd``/``usd``) plus optional time/side/qty/risk columns, matched on
   header aliases.
3. **JSON list of trade dicts** — the ``research/*_ledger.json`` shape
   (``{"d": day, "usd": pnl, "side": ..., "qty": ..., "risk": ...}``), same
   alias table as the CSV path.
4. **JSON list of numbers** — a bare P&L series (``onyx-lab``'s ``--pnls``
   contract). Timeless: one trade per element, sequence order preserved.
5. **Nested JSON** — a dict whose values are any of the above; ``key=`` picks
   the arm (``load(path, key="4xATR 1:4")``).

An unreadable or empty source RAISES. A source whose P&L column cannot be
identified RAISES with the headers it saw — it never falls back to a guess,
because a silently mis-read column produces a plausible, wrong report card.
"""
from __future__ import annotations

import calendar
import csv
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["Trade", "load", "load_rows", "LedgerError"]


class LedgerError(ValueError):
    """A ledger could not be read as trades. Always names what was seen."""


@dataclass
class Trade:
    entry_ts: Optional[int]
    exit_ts: Optional[int]
    side: str
    qty: Optional[float]
    pnl: float
    runup: Optional[float] = None
    drawdown: Optional[float] = None
    risk: Optional[float] = None
    cost: Optional[float] = None


# --- header aliases ----------------------------------------------------------
# Ordered: the first alias present in a header row wins.
_PNL_KEYS = ("pnl_usd", "net_pnl_usd", "net_pnl", "pnl", "profit_usd", "profit",
             "net_usd", "usd", "net", "p&l", "pl")
_ENTRY_TS_KEYS = ("entry_time", "entry_ts", "entry", "time", "date", "t", "d",
                  "datetime", "date_and_time", "date/time", "timestamp")
_EXIT_TS_KEYS = ("exit_time", "exit_ts", "exit")
_SIDE_KEYS = ("side", "direction", "dir", "type", "entry_id", "l/s")
_QTY_KEYS = ("qty", "quantity", "contracts", "size_qty", "size", "n_contracts")
_RUNUP_KEYS = ("runup", "run_up", "mfe", "max_runup", "favorable_excursion_usd",
               "run-up_usd")
_DRAWDOWN_KEYS = ("drawdown", "draw_down", "mae", "max_drawdown",
                  "adverse_excursion_usd", "drawdown_usd")
_RISK_KEYS = ("risk", "risk_usd", "r_usd", "risked")
_ENTRY_PX_KEYS = ("entry_price", "entry_px", "entry_fill", "price_in")
_EXIT_PX_KEYS = ("exit_price", "exit_px", "exit_fill", "price_out")
_COMMISSION_KEYS = ("commission", "fees", "cost", "commission_usd")
# TradingView's two-rows-per-trade "List of trades" export.
_TRADE_ID_KEYS = ("trade_number", "trade_", "trade_id", "trade", "tradenumber")
_ROW_PX_KEYS = ("price_usd", "price")

_SHORT_WORDS = ("short", "sell", "sld")
_LONG_WORDS = ("long", "buy", "bot")


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9&_/]", "", str(k).strip().lower().replace(" ", "_"))


def _pick(keys: Sequence[str], available: Dict[str, str]) -> Optional[str]:
    for k in keys:
        if k in available:
            return available[k]
    return None


def _to_float(v: Any) -> Optional[float]:
    """Parse a number the way exports write them: '1,675', '$-40.50', '(12)'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/a", "-", "--"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("$", "").replace("%", "").strip()
    if not s:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


_ISO_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"                  # date
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?"    # optional time
    r"\s*(Z|[+-]\d{2}:?\d{2})?"                 # optional offset
)


def _to_ts(v: Any) -> Optional[int]:
    """Epoch seconds (UTC) from an ISO string, epoch number, or epoch-ms number.

    A naive timestamp is read as UTC — the same convention the engine and
    ``onyx.lab.metrics`` use. An explicit offset is honored.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        n = float(v)
        if n > 1e12:        # milliseconds
            n /= 1000.0
        return int(n) if n > 0 else None
    s = str(v).strip()
    if not s:
        return None
    m = _ISO_RE.match(s)
    if not m:
        n = _to_float(s)
        return _to_ts(n) if n and n > 1e8 else None
    y, mo, d, hh, mm, ss, off = m.groups()
    ts = calendar.timegm((int(y), int(mo), int(d), int(hh or 0), int(mm or 0),
                          int(ss or 0), 0, 0, 0))
    if off and off != "Z":
        sign = 1 if off[0] == "+" else -1
        off = off[1:].replace(":", "")
        ts -= sign * (int(off[:2]) * 3600 + int(off[2:4] or 0) * 60)
    return ts


def _to_side(v: Any) -> Optional[str]:
    """Side from an explicit token, or None when the value carries no signal.

    TV writes ``L``/``S`` entry ids, but a strategy that names its entries
    ("PbD b break 21124.25") gives nothing — those return None so the caller can
    fall back to price direction rather than defaulting a short book to long.
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if any(w in s for w in _SHORT_WORDS):
        return "short"
    if any(w in s for w in _LONG_WORDS):
        return "long"
    if s in ("l", "s", "-1", "1"):
        return "short" if s in ("s", "-1") else "long"
    return None


def _side_from_prices(entry_px: Optional[float], exit_px: Optional[float],
                      pnl: float, commission: Optional[float]) -> Optional[str]:
    """Infer side from which way price moved vs which way the trade profited.

    Uses GROSS P&L (net + commission): a small winner turned negative by fees
    would otherwise invert the inference. Long iff price and gross agree in sign.
    """
    if entry_px is None or exit_px is None:
        return None
    move = exit_px - entry_px
    gross = pnl + (commission or 0.0)
    if move == 0 or gross == 0:
        return None
    return "long" if (move > 0) == (gross > 0) else "short"


def _row_to_trade(row: Dict[str, Any], cols: Dict[str, str],
                  pnl_col: str) -> Optional[Trade]:
    pnl = _to_float(row.get(pnl_col))
    if pnl is None:
        return None
    entry = _to_ts(row.get(cols["entry"])) if cols["entry"] else None
    exit_ = _to_ts(row.get(cols["exit"])) if cols["exit"] else None
    side = _to_side(row.get(cols["side"])) if cols["side"] else None
    if side is None:
        side = _side_from_prices(
            _to_float(row.get(cols["entry_px"])) if cols["entry_px"] else None,
            _to_float(row.get(cols["exit_px"])) if cols["exit_px"] else None,
            pnl,
            _to_float(row.get(cols["commission"])) if cols["commission"] else None,
        )
    return Trade(
        entry_ts=entry,
        exit_ts=exit_ if exit_ is not None else entry,
        side=side or "long",
        qty=_to_float(row.get(cols["qty"])) if cols["qty"] else None,
        pnl=pnl,
        runup=_to_float(row.get(cols["runup"])) if cols["runup"] else None,
        drawdown=_to_float(row.get(cols["drawdown"])) if cols["drawdown"] else None,
        risk=_to_float(row.get(cols["risk"])) if cols["risk"] else None,
        cost=_to_float(row.get(cols["commission"])) if cols["commission"] else None,
    )


def _pair_entry_exit(rows: List[Dict[str, Any]], available: Dict[str, str],
                     *, source: str) -> Optional[List[Dict[str, Any]]]:
    """Collapse TradingView's two-rows-per-trade export into one row per trade.

    TV's "List of trades" export writes an Entry row and an Exit row per trade.
    Newer exports repeat the trade-level P&L and commission on BOTH rows, so
    reading them row-per-trade doubles every number in the report.

    Returns None when the file is not that shape (every other source falls
    through to the normal one-row-per-trade path). Once the shape IS detected
    there is no silent fallback: a broken pair RAISES, because falling back
    would produce a plausible, doubled report card.
    """
    id_col = _pick(_TRADE_ID_KEYS, available)
    type_col = available.get("type")
    if not id_col or not type_col:
        return None
    groups: Dict[str, Dict[str, Dict[str, Any]]] = {}
    order: List[str] = []
    for r in rows:
        tid = str(r.get(id_col, "")).strip()
        kind = str(r.get(type_col, "")).strip().lower()
        kind = ("entry" if kind.startswith("entry")
                else "exit" if kind.startswith("exit") else None)
        if not tid or kind is None:
            return None                      # not the TV shape
        if tid not in groups:
            groups[tid] = {}
            order.append(tid)
        if kind in groups[tid]:
            raise LedgerError(
                "%s: trade %s has two %s rows — cannot pair entries to exits"
                % (source, tid, kind))
        groups[tid][kind] = r

    dt_col = _pick(_ENTRY_TS_KEYS, available)
    px_col = _pick(_ROW_PX_KEYS, available)
    out: List[Dict[str, Any]] = []
    for tid in order:
        g = groups[tid]
        if "exit" not in g:
            continue                         # still open at the end of the run
        if "entry" not in g:
            raise LedgerError("%s: trade %s has an exit row but no entry row"
                              % (source, tid))
        e, x = g["entry"], g["exit"]
        merged = dict(x)                     # exit row carries the trade totals
        if dt_col:
            merged["entry_time"] = e.get(dt_col)
            merged["exit_time"] = x.get(dt_col)
        if px_col:
            merged["entry_price"] = e.get(px_col)
            merged["exit_price"] = x.get(px_col)
        if "side" not in available:
            merged["side"] = e.get(type_col)
        out.append(merged)
    if not out:
        raise LedgerError("%s: TradingView export has no closed trades" % source)
    return out


def load_rows(rows: List[Dict[str, Any]], *, source: str = "rows") -> List[Trade]:
    """Normalize a list of dict rows (CSV records or JSON trade dicts)."""
    if not rows:
        raise LedgerError("%s: no rows" % source)
    available = {_norm_key(k): k for k in rows[0]}
    paired = _pair_entry_exit(rows, available, source=source)
    if paired is not None:
        rows = paired
        available = {_norm_key(k): k for k in rows[0]}
    pnl_col = _pick(_PNL_KEYS, available)
    if pnl_col is None:
        raise LedgerError(
            "%s: no P&L column found. Looked for %s; the file has %s"
            % (source, ", ".join(_PNL_KEYS), ", ".join(sorted(available)) or "(none)")
        )
    cols = {
        "entry": _pick(_ENTRY_TS_KEYS, available),
        "exit": _pick(_EXIT_TS_KEYS, available),
        "side": _pick(_SIDE_KEYS, available),
        "qty": _pick(_QTY_KEYS, available),
        "runup": _pick(_RUNUP_KEYS, available),
        "drawdown": _pick(_DRAWDOWN_KEYS, available),
        "risk": _pick(_RISK_KEYS, available),
        "entry_px": _pick(_ENTRY_PX_KEYS, available),
        "exit_px": _pick(_EXIT_PX_KEYS, available),
        "commission": _pick(_COMMISSION_KEYS, available),
    }
    out = [t for t in (_row_to_trade(r, cols, pnl_col) for r in rows) if t]
    if not out:
        raise LedgerError("%s: found column %r but no numeric values in it"
                          % (source, pnl_col))
    return out


def _from_json(data: Any, *, source: str, key: Optional[str]) -> List[Trade]:
    if isinstance(data, dict):
        if key is not None:
            if key not in data:
                raise LedgerError("%s: key %r not found. Available: %s"
                                  % (source, key, ", ".join(sorted(map(str, data)))))
            return _from_json(data[key], source="%s[%s]" % (source, key), key=None)
        # Single-armed dict: unwrap. Multi-armed: make the user choose.
        arms = [k for k, v in data.items() if isinstance(v, (list, dict))]
        if len(arms) == 1:
            return _from_json(data[arms[0]], source="%s[%s]" % (source, arms[0]),
                              key=None)
        raise LedgerError(
            "%s: JSON object with %d arms — pass key=<arm> to pick one. "
            "Available: %s" % (source, len(arms), ", ".join(sorted(map(str, arms))))
        )
    if not isinstance(data, list) or not data:
        raise LedgerError("%s: expected a non-empty list of trades" % source)
    if all(isinstance(x, (int, float)) for x in data):
        return [Trade(None, None, "long", None, float(x)) for x in data]
    if all(isinstance(x, dict) for x in data):
        return load_rows(data, source=source)
    raise LedgerError("%s: list mixes numbers and objects — expected one or the "
                      "other" % source)


def load(path: str, *, key: Optional[str] = None) -> List[Trade]:
    """Read ``path`` (``.csv`` or ``.json``) into canonical trades.

    ``key`` selects one arm out of a nested JSON result file. Raises
    ``LedgerError`` with the headers/keys it saw rather than guessing.
    """
    if not os.path.isfile(path):
        raise LedgerError("no such ledger file: %s" % path)
    name = os.path.basename(path)
    if path.lower().endswith(".json"):
        with open(path, "r") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as e:
                raise LedgerError("%s: not valid JSON (%s)" % (name, e))
        return _from_json(data, source=name, key=key)
    with open(path, "r", newline="", encoding="utf-8-sig") as fh:  # TV exports carry a BOM
        rows = list(csv.DictReader(fh))
    return load_rows(rows, source=name)


def resize(trades: List[Trade], risk_usd: float) -> List[Trade]:
    """Scale every trade to ``risk_usd`` of risk, per-trade.

    Only valid when the source recorded what it risked: each trade is scaled by
    ``risk_usd / trade.risk``. A ledger without a risk column RAISES — a global
    fudge factor would silently invent a sizing model and produce a confident,
    wrong pass rate. Use the strategy's own runner (which sizes natively) or
    pass the ledger through as-is instead.
    """
    missing = sum(1 for t in trades if not t.risk)
    if missing:
        raise LedgerError(
            "cannot re-size to $%g/trade: %d of %d trades have no risk recorded. "
            "Re-run the strategy at that risk (its sizing is native), or report "
            "the ledger as-is." % (risk_usd, missing, len(trades))
        )
    out = []
    for t in trades:
        k = risk_usd / t.risk
        out.append(Trade(
            entry_ts=t.entry_ts, exit_ts=t.exit_ts, side=t.side,
            qty=(t.qty * k) if t.qty is not None else None,
            pnl=t.pnl * k,
            runup=(t.runup * k) if t.runup is not None else None,
            drawdown=(t.drawdown * k) if t.drawdown is not None else None,
            risk=risk_usd,
            cost=(t.cost * k) if t.cost is not None else None,
        ))
    return out


def apply_cost(trades: List[Trade], *, per_contract: Optional[float] = None,
               per_trade: Optional[float] = None) -> List[Trade]:
    """Stamp each trade with the friction already embedded in its P&L.

    Exactly one of ``per_contract`` (USD round-turn per contract) or
    ``per_trade`` (flat USD) must be given. ``per_contract`` is the honest unit
    whenever the ledger records ``qty`` — a book whose size ranges 2 to 74
    contracts pays wildly different friction per trade, and a flat figure would
    put most of the ladder's cost on the wrong trades.

    This does NOT change ``pnl``: the ledger is already net of these costs at
    the 1x rung. It records what that 1x was so the rungs can be re-derived.
    """
    if (per_contract is None) == (per_trade is None):
        raise LedgerError("apply_cost needs exactly one of per_contract / per_trade")
    if per_trade is not None:
        return [Trade(**{**t.__dict__, "cost": float(per_trade)}) for t in trades]
    missing = sum(1 for t in trades if t.qty is None)
    if missing:
        raise LedgerError(
            "cost per contract needs a qty on every trade: %d of %d have none. "
            "Use a flat per-trade cost instead if that is the right unit."
            % (missing, len(trades))
        )
    return [Trade(**{**t.__dict__, "cost": float(per_contract) * t.qty})
            for t in trades]


def daily_pnls(trades: List[Trade]) -> List[float]:
    """Realized USD per calendar UTC day, in date order, days with trades only.

    A trade lands on its EXIT day (realization), matching ``onyx.lab.metrics``.
    Timeless ledgers (a bare P&L list) RAISE — a day-based prop race cannot be
    run without knowing which trades shared a day.
    """
    if any(t.exit_ts is None for t in trades):
        raise LedgerError(
            "ledger has no timestamps, so trades cannot be grouped into days — "
            "the prop sim needs a dated ledger (CSV export or *_ledger.json), "
            "not a bare P&L list."
        )
    by_day: Dict[int, float] = {}
    for t in trades:
        by_day[t.exit_ts // 86400] = by_day.get(t.exit_ts // 86400, 0.0) + t.pnl
    return [by_day[d] for d in sorted(by_day)]


def cost_per_day(trades: List[Trade]) -> List[float]:
    """Friction per trading day, aligned index-for-index with ``daily_pnls``."""
    if any(t.exit_ts is None for t in trades):
        raise LedgerError("ledger has no timestamps, so costs cannot be "
                          "grouped into days")
    by_day: Dict[int, float] = {}
    for t in trades:
        d = t.exit_ts // 86400
        by_day[d] = by_day.get(d, 0.0) + (t.cost or 0.0)
    return [by_day[d] for d in sorted(by_day)]


def attach_intraday_lows(days: List[float], trades: List["Trade"],
                         path: str) -> List[tuple]:
    """Pair each trading day with its intraday equity LOW -> [(close, low), ...].

    ``path`` is a CSV with ``date`` (YYYY-MM-DD) and ``low`` columns, where
    ``low`` is the most negative the book's running day P&L ever reached
    MARKED TO MARKET — realized plus open positions. It cannot be derived from
    a trade ledger: overlapping legs mean the worst moment of the book is not
    the sum of each trade's worst moment, so it has to be measured bar by bar
    and handed in.

    A day present in the ledger but missing from the file keeps ``low = close``
    (no intraday information -> cannot breach intraday), and the count of such
    days is raised rather than silently assumed, because quietly defaulting
    would understate exactly the risk this flag exists to measure.
    """
    import csv as _csv
    import datetime as _dt
    if any(t.exit_ts is None for t in trades):
        raise LedgerError("intraday lows need a dated ledger")
    order = sorted({t.exit_ts // 86400 for t in trades})
    lows: Dict[int, float] = {}
    with open(path) as fh:
        for row in _csv.DictReader(fh):
            d = _dt.date.fromisoformat(row["date"].strip()[:10])
            lows[int(_dt.datetime.combine(d, _dt.time()).replace(
                tzinfo=_dt.timezone.utc).timestamp()) // 86400] = float(row["low"])
    missing = [d for d in order if d not in lows]
    if len(missing) > len(order) * 0.05:
        raise LedgerError(
            "%d of %d trading days have no intraday low in %s — refusing to "
            "assume they never went underwater" % (len(missing), len(order), path))
    return [(c, min(c, lows.get(d, c))) for c, d in zip(days, order)]
