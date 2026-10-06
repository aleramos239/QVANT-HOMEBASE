"""A finished run bundle from a plain trade list: how a result of the research engine gets onto the tester
page. The page lists the runs folder on every call (RunManager.runs_list), so a bundle written here is listed,
opened, charted, compared and re-scored like any run -- and it says, wherever a run says what made it, that
the research engine did:

    range.label    "Research engine · <the dates>"    the Recent runs row, the compare chips, Properties
    engine         "research engine (imported)"       fill_law: the engine's own fills, nothing replayed here
    imported       {source, note, trades}             in run.json and in request.json
    propsim        {"skipped": ...}                   no prop eval is made up for it: the page's Eval picker
                                                      scores it on request (end-of-day rule); the blueprint's
                                                      own odds count open losses (blueprint_sim)

A trade is a dict: its entry and exit time (entry_ns | entry_ms | entry_time, the same for exit; a time is ISO
8601, New York wall clock when it carries no offset), side ("long" | "short"), qty, entry_price, exit_price and
net (dollars, after costs). The engine's own rows carry more (date, exit_reason, order_price, sl, tp, gross,
commission, mae/mfe): what a run's trade row has a place for is kept, the rest is dropped. A row without
mae_usd keeps it null -- never 0, which a prop re-score would read as "it never dipped".

Trades are stored as a run's are, by exit time then entry time: a trade's number on the page (and the
trade_index of show_on_chart) is its place in that order.

    python -m homebase.backtest.importrun TRADES.json --strategy draft_<name> --root NQ [--name ...]
        [--start YYYY-MM-DD --end YYYY-MM-DD] [--sessions N] [--note ...] [--base DIR]     -> prints the run id
TRADES.json = the list, or {"trades": [...]}. Nothing runs here and no tape is read: a list in, files out.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from . import discipline, report
from .runner import default_base, write_json

ET = ZoneInfo("America/New_York")
SOURCE = "research engine"
ENGINE = "research engine (imported)"
FILL_LAW = "the research engine's own fills (an imported trade list: nothing was replayed here)"
LABEL = "Research engine"
NOT_SCORED = ("not scored: this run was imported from the research engine. Pick an eval to score it with the "
              "page's end-of-day rule; the blueprint's own odds (open losses counted) are blueprint_sim.")
MIN_NS = 60_000_000_000
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
_STRATEGY = re.compile(r"^[a-z][a-z0-9_]{0,79}$")          # the middle of a run id (runner.RUN_ID)
_ROOT = re.compile(r"^[A-Z0-9]{1,6}$")


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _ns(t: dict, which: str, i: int) -> int:
    """A trade's entry or exit as epoch ns, from <which>_ns, <which>_ms or <which>_time."""
    for key, to_ns in ((f"{which}_ns", 1), (f"{which}_ms", 1_000_000)):
        if t.get(key) is not None:
            if type(t[key]) is not int or t[key] <= 0:
                raise ValueError(f"trade {i}: {key}: a whole number")
            return t[key] * to_ns
    try:
        d = dt.datetime.fromisoformat(t.get(f"{which}_time").replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError(f"trade {i}: {which} time: {which}_ns, {which}_ms, or {which}_time as ISO 8601 "
                         "(2024-03-05T09:30:01)") from None
    if d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    return (d - _EPOCH) // dt.timedelta(microseconds=1) * 1000


def _row(i: int, t) -> dict:
    """One plain trade as a run's trade row (engine.Trade's fields). A ValueError names the trade, from 1."""
    if not isinstance(t, dict):
        raise ValueError(f"trade {i}: an object with entry and exit time, side, qty, entry_price, exit_price, net")

    def need(key) -> float:
        if not _number(t.get(key)):
            raise ValueError(f"trade {i}: {key}: a number")
        return float(t[key])

    def opt(key):
        return None if t.get(key) is None else need(key)

    entry, exit_ = _ns(t, "entry", i), _ns(t, "exit", i)
    if exit_ < entry:
        raise ValueError(f"trade {i}: it exits before it enters")
    if t.get("side") not in ("long", "short"):
        raise ValueError(f"trade {i}: side: long or short")
    if type(t.get("qty")) is not int or t["qty"] < 1:
        raise ValueError(f"trade {i}: qty: a whole number of contracts, 1 or more")
    try:
        date = (dt.datetime.fromtimestamp(entry / 1e9, ET).date() if t.get("date") is None
                else dt.date.fromisoformat(t["date"])).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"trade {i}: date: the session date, YYYY-MM-DD") from None
    net, commission = need("net"), opt("commission") or 0.0
    gross = opt("gross")
    return {"date": date, "side": t["side"], "qty": t["qty"], "entry_ns": entry, "entry_price": need("entry_price"),
            "exit_ns": exit_, "exit_price": need("exit_price"), "exit_reason": str(t.get("exit_reason") or ""),
            "order_price": opt("order_price"), "sl": opt("sl"), "tp": opt("tp"),
            "gross": net + commission if gross is None else gross, "commission": commission, "net": net,
            "mae_pts": opt("mae_pts"), "mfe_pts": opt("mfe_pts"), "mae_usd": opt("mae_usd"), "mfe_usd": opt("mfe_usd"),
            "bars": int(exit_ // MIN_NS - entry // MIN_NS + 1), "seconds": round((exit_ - entry) / 1e9, 3)}


def write_run(trades, *, strategy: str, root: str, name: str | None = None, base: Path | None = None,
              start=None, end=None, inputs: dict | None = None, qty: int | None = None, commission: float = 4.00,
              slippage_ticks: float = 1.0, capital: float = 50_000.0, sessions: int | None = None,
              note: str = "") -> str:
    """Write runs/<id>/ under `base` (default: the tester's own folder, where the page looks) from `trades`,
    and return the run id. The folder appears whole or not at all.

      strategy, root, name   the id the run is listed under (the idea's Lab draft: draft_<name>), the futures
                             root its trades are drawn on, and the name it shows (default: the id)
      start, end             the session dates the result covers (default: the first and the last trade's);
                             every trade lies inside them
      sessions               the session days the engine ran (default: the days that traded -- a trade list
                             does not know the flat ones)
      qty, commission, slippage_ticks, capital, inputs
                             what the engine ran with: LABELS on the run (capital is also the base of its %
                             figures). The nets are the engine's and are never touched. Defaults: the largest
                             qty in the list; $4.00 a round turn and 1 tick (the engine's normal fills, and the
                             tester's own); $50,000
    ValueError on a list or a label that does not read; nothing is written then."""
    if not isinstance(trades, list):
        raise ValueError("trades: a list of trades")
    if not trades:
        raise ValueError("no trades: there is nothing to show")
    if not isinstance(strategy, str) or not _STRATEGY.fullmatch(strategy):
        raise ValueError("strategy: the id the run is listed under, a-z 0-9 _ (e.g. draft_nq_orb_15)")
    if not isinstance(root, str) or not _ROOT.fullmatch(root):
        raise ValueError("root: a futures root such as NQ")
    name = strategy if name is None else name
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or not name.isprintable():
        raise ValueError("name: one line, at most 80 characters")
    if inputs is not None and not isinstance(inputs, dict):
        raise ValueError("inputs: a JSON object")
    rows = [_row(i, t) for i, t in enumerate(trades, 1)]
    days = sorted({t["date"] for t in rows})
    rng = discipline.parse_range({"kind": "custom", "start": start or days[0], "end": end or days[-1]})
    for i, t in enumerate(rows, 1):
        if not rng.start.isoformat() <= t["date"] <= rng.end.isoformat():
            raise ValueError(f"trade {i} is on {t['date']}, outside {rng.start} → {rng.end}")
    if (rng.start, rng.end) == (discipline.RESEARCH_START, discipline.RESEARCH_END):
        rng = discipline.parse_range({"kind": "research"})          # the build days read as the build days
    qty = max(t["qty"] for t in rows) if qty is None else qty
    if type(qty) is not int or qty < 1:
        raise ValueError("qty: a whole number of contracts, 1 or more")
    if not _number(commission) or commission < 0:
        raise ValueError("commission: dollars per round turn, 0 or more")
    if not _number(slippage_ticks) or slippage_ticks < 0:
        raise ValueError("slippage_ticks: 0 or more")
    if not _number(capital) or capital <= 0:
        raise ValueError("capital: the account size in dollars, above 0")
    sessions = len(days) if sessions is None else sessions
    if type(sessions) is not int or sessions < len(days):
        raise ValueError(f"sessions: the session days the engine ran, at least the {len(days)} that traded")

    rows.sort(key=lambda t: (t["exit_ns"], t["entry_ns"]))
    rid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{strategy}-{secrets.token_hex(2)}"
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    label = {**rng.to_dict(), "label": f"{LABEL} · {rng.label}"}
    mark = {"source": SOURCE, "note": str(note or ""), "trades": len(rows)}
    shared = {"inputs": dict(inputs or {}), "strategy_config": {}, "range": label, "qty": qty,
              "commission": float(commission), "slippage_ticks": float(slippage_ticks), "capital": float(capital),
              "prop_rules": None, "imported": mark}
    meta = {"id": rid, "created": now, "finished": now, "engine": ENGINE, "fill_law": FILL_LAW,
            "strategy": {"id": strategy, "name": name, "root": root}, **shared,
            # `holdout`: these trades are on the test days -- a fact on the report, as on any run
            "holdout": rng.holdout, "holdout_reason": None, "propsim_error": False,
            "coverage": {"sessions": sessions, "used": sessions, "skipped": [], "skipped_by_reason": {},
                         "no_trade": [], "skipped_by_error": 0, "skipped_by_data": 0},
            "report": report.build(rows, float(capital))}
    base = Path(base) if base is not None else default_base()
    tmp = base / "runs" / f".{rid}.import"         # not a run id: the page never lists a run half-written
    tmp.mkdir(parents=True)
    try:
        write_json(tmp / "request.json", {"strategy": strategy, **shared, "id": rid, "created": now})
        write_json(tmp / "equity.json", report.equity(rows))         # needs ns: the ms conversion is last
        write_json(tmp / "trades.json", report.to_ms(rows))
        write_json(tmp / "plots.json", {"plots": {}, "hlines": []})
        write_json(tmp / "propsim.json", {"skipped": NOT_SCORED})
        write_json(tmp / "run.json", meta)
        write_json(tmp / "status.json", {"id": rid, "status": "done", "phase": "done", "done": sessions,
                                         "total": sessions, "updated": now})
        os.replace(tmp, base / "runs" / rid)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:        # a run whose dates reach the test days is recorded, like any run (a record, never a gate)
        discipline.record(base / "spends.jsonl", strategy=strategy, inputs=shared["inputs"], rng=rng, run_id=rid)
    except OSError as e:
        print(f"importrun: could not append to the spend log: {e} (the run is imported)", file=sys.stderr, flush=True)
    return rid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.backtest.importrun",
                                 description="Write a finished tester run from a trade list of the research engine.")
    ap.add_argument("trades", type=Path, help='a JSON file: the trade list, or {"trades": [...]}')
    ap.add_argument("--strategy", required=True, help="the id the run is listed under, e.g. draft_<idea name>")
    ap.add_argument("--root", required=True, help="the futures root, e.g. NQ")
    ap.add_argument("--name", help="the name the run shows (default: the id)")
    ap.add_argument("--start", help="YYYY-MM-DD (default: the first trade's session)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: the last trade's session)")
    ap.add_argument("--sessions", type=int, help="the session days the engine ran (default: the days that traded)")
    ap.add_argument("--note", default="", help="a line kept with the run")
    ap.add_argument("--base", type=Path, default=None, help="the tester's base folder (default: the app's own)")
    a = ap.parse_args(argv)
    try:
        data = json.loads(a.trades.read_text(encoding="utf-8"))
        rid = write_run(data.get("trades") if isinstance(data, dict) else data, strategy=a.strategy, root=a.root,
                        name=a.name, base=a.base, start=a.start, end=a.end, sessions=a.sessions, note=a.note)
    except (OSError, ValueError) as e:
        print(f"importrun: {e}", file=sys.stderr)
        return 2
    print(rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
