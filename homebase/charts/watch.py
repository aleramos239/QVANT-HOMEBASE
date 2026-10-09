"""The Desk's WATCH list: Book strategies the owner promoted from the Lab (2026-10-09).

A watched strategy is a RECORD, never an algo: a snapshot of its Book card and of its equity curve, shown under Strategies on the
Desk page with its numbers and a button that opens its executions on the chart. It places no order and nothing here can make it:
the desk's engine does not read this folder. Promote writes one file, Remove deletes it, and a strategy can be promoted again.

    <root>/<name>.json      root = HOMEBASE_WATCH_ROOT, else ~/.homebase/watch
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

ENV_ROOT = "HOMEBASE_WATCH_ROOT"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,33}$")          # a pipeline card's name (pipeline_tools.NAME_RE)
CARD_KEYS = ("name", "sub", "family", "source", "why", "market", "session", "bar", "filter", "label", "hours", "win_days_month",
             "winning_months", "biggest_day_share", "tries", "prop")
CURVE_KEYS = ("period", "cell", "side", "start", "end", "trades", "days", "net", "win_rate", "avg_trade", "avg_win", "avg_loss",
              "profit_factor", "best_day", "worst_day", "max_drawdown", "curve")


def root(arg=None) -> Path:
    v = arg or os.environ.get(ENV_ROOT)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "watch"


def _file(name: str, at=None) -> Path:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError("name: a Book strategy's name -- a-z, 0-9 and '_' (a letter first)")
    return root(at) / f"{name}.json"


def snapshot(card: dict, curve: dict, now: dt.datetime | None = None) -> dict:
    """What is kept of a Book card and its curve when it is promoted: the facts the Desk page shows, nothing that runs."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return {**{k: card.get(k) for k in CARD_KEYS}, **{k: curve.get(k) for k in CURVE_KEYS},
            "promoted_utc": now.isoformat(timespec="seconds"), "watch_only": True}


def put(snap: dict, at=None) -> dict:
    f = _file(snap.get("name"), at)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    tmp.write_text(json.dumps(snap), encoding="utf-8")
    os.replace(tmp, f)                               # whole or not at all
    return snap


def get(name: str, at=None) -> dict | None:
    try:
        got = json.loads(_file(name, at).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def remove(name: str, at=None) -> bool:
    """True when it was on the list. A file that is not there is not an error: the page may be a step behind."""
    try:
        _file(name, at).unlink()
        return True
    except FileNotFoundError:
        return False


def listing(at=None) -> list:
    """Every watched strategy, the latest promoted first; a file that does not read is left out."""
    d = root(at)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        if NAME_RE.fullmatch(f.stem):
            got = get(f.stem, at)
            if got is not None and got.get("name") == f.stem:
                out.append(got)
    return sorted(out, key=lambda s: str(s.get("promoted_utc") or ""), reverse=True)
