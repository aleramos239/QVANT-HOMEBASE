"""pay_accounts.py -- THE ACCOUNTS the set is scored on: <pipeline root>/payout/accounts.json, one entry a funded account of the Desk.

  folder(root=None) -> <pipeline root>/payout (made when asked for)
  sync(root=None, desk=None) -> the accounts, after a look at the Desk
        A NEW account of the Desk's config that is neither paper nor the owner's own live account is added with the rule file it is
        scored on when nobody has said (pay_rules `accounts`: a Lucid account = the pipeline's own account, an Apex funded account =
        the newest Apex Legacy file of its size) and `assumed` true. Every account's `balance`, `peak` (its highest recorded
        end-of-day balance) and `asof` are read again from the Desk's daily balance record. `rules`, `on` and `assumed` are THE
        OWNER'S: a sync never changes them. A Desk that cannot be read changes nothing.
        desk = (labels, {label: {date: balance}}) for a test; default = the app's config.json (labels and two flags only) and its
        equity.jsonl.
  load(root=None) -> the accounts on file (no look at the Desk); none on file = []
  start(account) -> {"profit", "peak"}: where the account stands, in dollars over its size (pay_score.walk's start)
  SIZES            the account sizes a first balance is rounded to

An account's size is its FIRST recorded balance, to the nearest size. Standard library; homebase/ is only read.
Locked by tests/test_pay_build.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import api
from . import pay_rules as PY
from . import pipe_rules as PR
from . import pipe_store as PS
from . import propodds as PO

FILE = "accounts.json"
SIZES = (25_000, 50_000, 100_000, 150_000, 250_000, 300_000)
FIRMS = (("PAAPEX", "apex"), ("APEX", "apex"), ("LT", "lucid"), ("LF", "lucid"))


def folder(root=None) -> Path:
    d = PS.root(root) / "payout"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _desk() -> tuple:
    """The Desk's funded accounts (their labels) and its daily balance record, or (None, None) when it cannot be read."""
    try:
        api.ideastore()
        import homebase
        from homebase import paths
        cfg = json.loads((Path(homebase.__file__).parent / "config.json").read_text(encoding="utf-8"))
        labels = [str(a.get("label") or k) for k, a in (cfg.get("accounts") or {}).items() if isinstance(a, dict) and not a.get("paper") and not a.get("live")]
        by: dict = {}
        with open(paths.state_dir() / "equity.jsonl", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    by.setdefault(str(row["account"]), {})[str(row["date"])] = float(row["equity"])
                except (ValueError, KeyError, TypeError):
                    continue
        return labels, by
    except (OSError, ValueError, ImportError, AttributeError):
        return None, None


def _firm(label: str):
    return next((f for start, f in FIRMS if label.upper().startswith(start)), None)


def _rules(firm, size):
    """The rule file a new account is scored on when the owner has not said, or None."""
    word = (PY.need("accounts") or {}).get(firm) if firm else None
    if firm == "lucid" and word is None:
        return PR.need("prop", "account")
    if not word or not size:
        return None
    start = word.format(k=size // 1000) + "@"
    ids = sorted(r["id"] for r in PO.app().list_rules() if str(r.get("id", "")).startswith(start))
    return ids[-1] if ids else None


def load(root=None) -> list:
    try:
        got = json.loads((PS.root(root) / "payout" / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [a for a in got.get("accounts", []) if isinstance(a, dict) and a.get("id")]


def sync(root=None, desk=None) -> list:
    labels, by = desk if desk is not None else _desk()
    have = {a["id"]: a for a in load(root)}
    if labels is None:
        return list(have.values())
    for label in labels:
        days = by.get(label) or {}
        a = have.get(label)
        if a is None:
            size = min(SIZES, key=lambda s: abs(s - days[min(days)])) if days else None
            firm = _firm(label)
            a = have[label] = {"id": label, "firm": firm, "size": size, "rules": _rules(firm, size), "assumed": True, "on": True}
        if days:
            last = max(days)
            a.update(balance=days[last], peak=max(days.values()), asof=last)
    for k, a in have.items():
        a["connected"] = k in labels
    out = list(have.values())
    PS._write(folder(root) / FILE, {"_about": "The funded accounts the payout pipeline scores a set on. `rules` (a rule file of the app's prop simulator), `on` "
                                              "and `assumed` are the owner's; the balances are read from the Desk.", "accounts": out})
    return out


def start(a: dict) -> dict:
    profit = float(a.get("balance") or a["size"]) - a["size"]
    return {"profit": profit, "peak": max(float(a.get("peak") or a["size"]) - a["size"], profit, 0.0)}
